# CKDO Dashboard v2 — Panduan Deployment

> **Server target:** `172.21.2.209`  
> **GitHub account:** `mashudizaini`  
> **Repository:** `https://github.com/mashudizaini/ckdo-dashboard-v2`

---

## Daftar Isi

1. [Arsitektur & Lingkungan](#1-arsitektur--lingkungan)
2. [Prasyarat Server](#2-prasyarat-server)
3. [Alur Lengkap: Laptop → GitHub → Server](#3-alur-lengkap-laptop--github--server)
   - [3A. Push kode dari VS Code ke GitHub](#3a-push-kode-dari-vs-code-ke-github)
   - [3B. Setup pertama kali di server](#3b-setup-pertama-kali-di-server)
   - [3C. Update / Redeploy (setelah setup)](#3c-update--redeploy-setelah-setup)
4. [Struktur File & Secrets](#4-struktur-file--secrets)
5. [Konfigurasi Nginx + SSL](#5-konfigurasi-nginx--ssl)
6. [Konfigurasi Keycloak](#6-konfigurasi-keycloak)
7. [Konfigurasi Email SMTP](#7-konfigurasi-email-smtp)
8. [Troubleshooting](#8-troubleshooting)
9. [Catatan Keamanan](#9-catatan-keamanan)

---

## 1. Arsitektur & Lingkungan

```
+------------------+------------------+------------------------------------------+
| Lingkungan       | Host             | URL                                      |
|------------------|------------------|------------------------------------------|
| Local (laptop)   | localhost        | http://localhost                         |
| Development      | 172.21.2.209     | https://dashboard-dev.ckd-otto.com       |
| Production       | (TBD)            | https://dashboard.ckd-otto.com           |
+------------------+------------------+------------------------------------------+
```

### Stack Docker

```
Browser
  └─→ Nginx (reverse proxy, SSL)
        ├─→ Frontend  (React + Vite)       port 3000
        ├─→ Backend   (FastAPI)            port 8000
        └─→ Keycloak  (Auth Server)        port 8080
              └─→ PostgreSQL               port 5432
Redis (cache + Celery broker)              port 6379
Oracle Instant Client (koneksi EBS)
```

---

## 2. Prasyarat Server

SSH ke server terlebih dahulu:
```bash
ssh user@172.21.2.209
```

### Install Docker

```bash
# Install Docker Engine
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker              # aktifkan group tanpa logout

# Verifikasi
docker --version           # harus 24.x ke atas
docker compose version     # harus 2.x ke atas
```

### Install Git

```bash
sudo apt install git -y
git --version
```

### Setup SSH Key untuk GitHub

```bash
# Buat SSH key di server
ssh-keygen -t ed25519 -C "server-dev-172.21.2.209"
# Tekan Enter untuk semua pertanyaan (pakai default)

# Tampilkan public key
cat ~/.ssh/id_ed25519.pub
```

Tambahkan public key tersebut ke GitHub:
1. Buka `https://github.com/mashudizaini` → **Settings** → **SSH and GPG keys**
2. Klik **New SSH key**
3. Title: `Dev Server 172.21.2.209`
4. Paste isi `id_ed25519.pub`
5. Klik **Add SSH key**

Verifikasi koneksi:
```bash
ssh -T git@github.com
# Harus muncul: Hi mashudizaini! You've successfully authenticated...
```

### Install Oracle Instant Client

Oracle Instant Client **tidak bisa di-push ke GitHub** (binary besar), harus disalin manual.

```bash
# Dari laptop, upload ke server
scp instantclient-basic-linux.x64-21.*.zip user@172.21.2.209:/tmp/

# Di server: ekstrak dan salin ke folder project
# (lakukan setelah clone repository di langkah 3B)
cd /tmp
unzip instantclient-basic-linux.x64-*.zip
cp instantclient_21_*/* /opt/ckdo/ckdo-dashboard-v2/oracle_client/
```

---

## 3. Alur Lengkap: Laptop → GitHub → Server

### 3A. Push Kode dari VS Code ke GitHub

Lakukan di **laptop**, bukan di server.

#### Pertama kali (setup repository)

```bash
# Di folder project d:\ckdo-dashboard-v2
# Pastikan .env ada di .gitignore
grep "\.env" .gitignore    # harus tampil baris ".env"

# Hubungkan ke GitHub
git remote add origin git@github.com:mashudizaini/ckdo-dashboard-v2.git

# Push pertama kali
git add .
git commit -m "Initial commit: CKDO Dashboard v2"
git push -u origin master
```

> ⚠ **PENTING:** Sebelum push, pastikan `git status` tidak menampilkan file `.env`.
> Kalau `.env` muncul di staged files, jalankan:
> ```bash
> git rm --cached .env
> git commit -m "Remove .env from tracking"
> ```

#### Update rutin (setelah ada perubahan kode)

Di VS Code, bisa lewat GUI Source Control atau terminal:

```bash
# Cek perubahan apa yang ada
git status
git diff

# Stage perubahan
git add .

# Commit dengan pesan yang jelas
git commit -m "feat: tambah fitur X" 
# atau: "fix: perbaiki bug Y"
# atau: "update: update halaman Z"

# Push ke GitHub
git push origin master
```

---

### 3B. Setup Pertama Kali di Server

SSH ke server:
```bash
ssh user@172.21.2.209
```

#### Langkah 1 — Clone repository

```bash
cd /opt
sudo mkdir -p ckdo
sudo chown $USER:$USER ckdo
cd ckdo

git clone git@github.com:mashudizaini/ckdo-dashboard-v2.git
cd ckdo-dashboard-v2
```

#### Langkah 2 — Buat file `.env`

```bash
cp .env.example .env
nano .env
```

Isi nilai yang perlu diubah (lihat bagian [Struktur File & Secrets](#4-struktur-file--secrets) untuk daftar lengkap):

```env
ENVIRONMENT=development
APP_URL=https://dashboard-dev.ckd-otto.com

POSTGRES_PASSWORD=GantiDenganPasswordKuat
DATABASE_URL=postgresql://postgres:GantiDenganPasswordKuat@postgres:5432/ckdo_dashboard

REDIS_PASSWORD=GantiRedisPassword
REDIS_URL=redis://:GantiRedisPassword@redis:6379/0
CELERY_BROKER_URL=redis://:GantiRedisPassword@redis:6379/1
CELERY_RESULT_BACKEND=redis://:GantiRedisPassword@redis:6379/2

KEYCLOAK_ADMIN_PASSWORD=GantiKeycloakPassword
KEYCLOAK_CLIENT_SECRET=GantiClientSecret

VITE_API_URL=https://dashboard-dev.ckd-otto.com/api/v1
VITE_KEYCLOAK_URL=https://dashboard-dev.ckd-otto.com
VITE_KEYCLOAK_REALM=ckdo
VITE_KEYCLOAK_CLIENT_ID=ckdo-dashboard
```

Tekan `Ctrl+X` → `Y` → `Enter` untuk simpan.

#### Langkah 3 — Salin Oracle Instant Client

```bash
# (Pastikan sudah diupload ke /tmp lebih dulu — lihat bagian Prasyarat)
cp /tmp/instantclient_21_*/* /opt/ckdo/ckdo-dashboard-v2/oracle_client/
ls oracle_client/*.so*    # harus muncul daftar file .so
```

#### Langkah 4 — Jalankan aplikasi

```bash
cd /opt/ckdo/ckdo-dashboard-v2

# Build dan start semua service
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

# Tunggu sekitar 2-3 menit, lalu cek status
docker compose ps
```

Output yang diharapkan (semua `running`):
```
NAME                  STATUS
ckdo_nginx            running
ckdo_frontend         running
ckdo_backend          running
ckdo_keycloak         running
ckdo_postgres         running
ckdo_redis            running
```

Jika ada yang `exited`, lihat log-nya:
```bash
docker compose logs keycloak --tail=50
docker compose logs backend --tail=50
```

#### Langkah 5 — Setup SSL (Let's Encrypt)

Pastikan DNS sudah diarahkan lebih dulu:
```
dashboard-dev.ckd-otto.com  →  A record  →  172.21.2.209
```

Verifikasi dari server:
```bash
ping dashboard-dev.ckd-otto.com   # harus resolve ke 172.21.2.209
```

Install SSL:
```bash
sudo apt install certbot -y

# Stop nginx sementara
docker compose stop nginx

# Request certificate
sudo certbot certonly --standalone \
  -d dashboard-dev.ckd-otto.com \
  --email mashudi.zaini@yahoo.com \
  --agree-tos --no-eff-email

# Restart nginx
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d nginx
```

#### Langkah 6 — Verifikasi

```bash
# Cek semua service jalan
docker compose ps

# Test akses API
curl https://dashboard-dev.ckd-otto.com/api/v1/health

# Lihat log real-time
docker compose logs -f backend --tail=30
```

Buka browser: `https://dashboard-dev.ckd-otto.com` — harus muncul halaman login CKDO Dashboard.

---

### 3C. Update / Redeploy (Setelah Setup)

Setelah ada perubahan kode yang sudah di-push ke GitHub:

```bash
ssh user@172.21.2.209
cd /opt/ckdo/ckdo-dashboard-v2

# Pull perubahan terbaru dari GitHub
git pull origin master

# Rebuild dan restart
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

# Cek status
docker compose ps
docker compose logs -f backend --tail=30
```

#### Jika hanya backend yang berubah (lebih cepat)

```bash
git pull origin master
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build backend celery
```

#### Jika ada perubahan environment variable di `.env`

```bash
nano .env          # edit nilai yang berubah
docker compose -f docker-compose.yml -f docker-compose.dev.yml down
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

> ⚠ **PENTING:** `VITE_*` env vars di-embed saat build frontend. Jika ada perubahan
> `VITE_*`, wajib rebuild frontend: `up -d --build frontend`

#### Rollback ke versi sebelumnya

```bash
git log --oneline -10              # lihat riwayat commit
git checkout <hash-commit-lama>    # kembali ke versi tertentu
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

---

## 4. Struktur File & Secrets

> **File `.env` TIDAK PERNAH masuk ke GitHub.**
> Setiap server punya `.env` sendiri yang dibuat manual dari `.env.example`.

### `.env.example` — Template (ada di git)

```env
# ─── APPLICATION ─────────────────────────────
ENVIRONMENT=development
APP_NAME=CKDO Dashboard
APP_URL=https://DOMAIN_ANDA

# ─── POSTGRESQL ──────────────────────────────
POSTGRES_USER=postgres
POSTGRES_PASSWORD=GANTI_INI
DATABASE_URL=postgresql://postgres:GANTI_INI@postgres:5432/ckdo_dashboard

# ─── REDIS ───────────────────────────────────
REDIS_PASSWORD=GANTI_INI
REDIS_URL=redis://:GANTI_INI@redis:6379/0
CELERY_BROKER_URL=redis://:GANTI_INI@redis:6379/1
CELERY_RESULT_BACKEND=redis://:GANTI_INI@redis:6379/2

# ─── KEYCLOAK ────────────────────────────────
KEYCLOAK_ADMIN=admin
KEYCLOAK_ADMIN_PASSWORD=GANTI_INI
KEYCLOAK_URL=http://keycloak:8080
KEYCLOAK_REALM=ckdo
KEYCLOAK_CLIENT_ID=ckdo-dashboard
KEYCLOAK_CLIENT_SECRET=GANTI_INI

# ─── ORACLE EBS ──────────────────────────────
ORACLE_HOST=172.21.2.201
ORACLE_PORT=1521
ORACLE_SERVICE=PROD
ORACLE_USER=apps
ORACLE_PASSWORD=GANTI_INI
ORACLE_INSTANT_CLIENT=/opt/oracle/instantclient

# ─── TALENTA HR API ──────────────────────────
TALENTA_API_KEY=GANTI_INI
TALENTA_API_URL=https://api.talenta.co

# ─── ANTHROPIC ───────────────────────────────
ANTHROPIC_API_KEY=GANTI_INI

# ─── SMTP ────────────────────────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=noreply@ckd-otto.com
SMTP_PASSWORD=GANTI_INI_APP_PASSWORD

# ─── FRONTEND (Vite — di-embed saat build) ───
VITE_API_URL=https://DOMAIN_ANDA/api/v1
VITE_KEYCLOAK_URL=https://DOMAIN_ANDA
VITE_KEYCLOAK_REALM=ckdo
VITE_KEYCLOAK_CLIENT_ID=ckdo-dashboard

# ─── METALS API ──────────────────────────────
METALS_API_KEY=GANTI_INI
```

### Lokasi penyimpanan secrets yang aman

Simpan nilai `.env` asli di:
- **Bitwarden** (rekomendasi — gratis, self-hostable)
- Shared folder internal yang akses-nya terbatas
- **Jangan** di grup WhatsApp / Telegram / email

---

## 5. Konfigurasi Nginx + SSL

### `nginx/nginx.dev.conf`

```nginx
worker_processes 1;
events {}

http {
  upstream backend  { server backend:8000; }
  upstream frontend { server frontend:3000; }
  upstream keycloak { server keycloak:8080; }

  # Redirect HTTP → HTTPS
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
    ssl_ciphers         HIGH:!aNULL:!MD5;

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
      client_max_body_size 50m;
    }

    # Keycloak Auth
    location /auth/ {
      proxy_pass http://keycloak/auth/;
      proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto https;
      proxy_buffer_size 128k;
      proxy_buffers 4 256k;
    }
  }
}
```

### Auto-renew SSL (cron)

```bash
# Edit cron root
sudo crontab -e

# Tambahkan baris ini:
0 3 * * * certbot renew --quiet && docker compose -C /opt/ckdo/ckdo-dashboard-v2 restart nginx
```

---

## 6. Konfigurasi Keycloak

### Login ke Keycloak Admin Console

```
URL:      https://dashboard-dev.ckd-otto.com/auth/admin
User:     admin
Password: (nilai KEYCLOAK_ADMIN_PASSWORD di .env)
```

### Update Client Redirect URIs

1. Buka: **Realm: ckdo** → **Clients** → **ckdo-dashboard** → tab **Settings**
2. Update field berikut:

| Field | Nilai |
|---|---|
| Root URL | `https://dashboard-dev.ckd-otto.com` |
| Valid Redirect URIs | `https://dashboard-dev.ckd-otto.com/*` |
| Valid Post Logout Redirect URIs | `https://dashboard-dev.ckd-otto.com/*` |
| Web Origins | `https://dashboard-dev.ckd-otto.com` |

3. Klik **Save**

### Ambil Client Secret

1. Tab **Credentials**
2. Copy nilai **Client Secret**
3. Update `.env` di server:
   ```bash
   nano /opt/ckdo/ckdo-dashboard-v2/.env
   # Update: KEYCLOAK_CLIENT_SECRET=nilai_yang_dicopy
   ```
4. Restart backend:
   ```bash
   cd /opt/ckdo/ckdo-dashboard-v2
   docker compose restart backend celery
   ```

### Export Realm (backup konfigurasi Keycloak)

Lakukan setelah ada perubahan konfigurasi Keycloak yang signifikan:

```bash
docker exec ckdo_keycloak /opt/keycloak/bin/kc.sh export \
  --realm ckdo \
  --file /tmp/realm-export.json

docker cp ckdo_keycloak:/tmp/realm-export.json \
  /opt/ckdo/ckdo-dashboard-v2/keycloak/realm-export.json
```

> Hapus nilai `secret` dari client credentials sebelum commit ke git.

---

## 7. Konfigurasi Email SMTP

### Buat App Password Google Workspace

1. Login ke `noreply@ckd-otto.com` di browser
2. **Manage your Google Account** → **Security**
3. Aktifkan **2-Step Verification** (wajib)
4. Security → **App Passwords**
5. Generate: App = **Mail**, Device = **Other** → isi "CKDO Dev Server"
6. Catat 16-karakter App Password (format: `xxxx xxxx xxxx xxxx`)

### Konfigurasi SMTP di Keycloak

1. Login Keycloak Admin Console
2. **Realm Settings** → **Email**

| Field | Nilai |
|---|---|
| From | `noreply@ckd-otto.com` |
| From Display Name | `CKDO Dashboard` |
| Host | `smtp.gmail.com` |
| Port | `587` |
| Encryption | `STARTTLS` |
| Authentication | Enabled |
| Username | `noreply@ckd-otto.com` |
| Password | *(App Password 16 karakter)* |

3. Klik **Test connection** → harus berhasil → **Save**

---

## 8. Troubleshooting

### Keycloak tidak mau start

```bash
docker compose logs keycloak --tail=50
# Sering karena PostgreSQL belum siap → tunggu 30 detik lalu:
docker compose restart keycloak
```

### Backend gagal konek ke Oracle

```bash
docker compose logs backend --tail=50
# Cek .so files ada di oracle_client/
ls /opt/ckdo/ckdo-dashboard-v2/oracle_client/*.so*
```

### Frontend tidak update setelah deploy

`VITE_*` env vars di-embed saat build — wajib rebuild:
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build frontend
```

### SSL expired

```bash
sudo certbot renew
docker compose restart nginx
```

### Port sudah dipakai (conflict)

```bash
sudo netstat -tlnp | grep -E "80|443|8080|5432"
# Matikan proses yang konflik, atau ganti port di docker-compose
```

### Reset total (HATI-HATI: semua data hilang!)

```bash
cd /opt/ckdo/ckdo-dashboard-v2
docker compose down -v    # -v menghapus volumes termasuk database!
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

### Cek penggunaan disk / resource

```bash
docker system df              # penggunaan disk Docker
docker stats --no-stream      # penggunaan CPU/RAM per container
df -h                         # disk server
```

---

## 9. Catatan Keamanan

- [ ] Ganti **semua** password default sebelum deploy ke server manapun
- [ ] Jangan pernah commit `.env` ke GitHub
- [ ] `KEYCLOAK_CLIENT_SECRET` harus berbeda antara dev dan production
- [ ] Batasi akses port 5432 (Postgres) dan 6379 (Redis) — tidak boleh expose ke public
- [ ] Rotate `ANTHROPIC_API_KEY` secara berkala
- [ ] App Password Google dibuat per-environment (satu untuk dev, satu untuk production)
- [ ] SSH ke server hanya via key pair, matikan password authentication

---

## Referensi Cepat

| Kebutuhan | Perintah |
|---|---|
| SSH ke server | `ssh user@172.21.2.209` |
| Lihat status service | `docker compose ps` |
| Lihat log realtime | `docker compose logs -f backend` |
| Pull + rebuild + restart | `git pull && docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build` |
| Restart satu service | `docker compose restart backend` |
| Masuk ke container | `docker exec -it ckdo_backend bash` |
| Backup database | `docker exec ckdo_postgres pg_dump -U postgres ckdo_dashboard > backup.sql` |
| Restore database | `docker exec -i ckdo_postgres psql -U postgres ckdo_dashboard < backup.sql` |

---

*Server: 172.21.2.209 · GitHub: mashudizaini · Terakhir diperbarui: 2026-04-21*
