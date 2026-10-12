# SOP Sinkronisasi Kode — Laptop · GitHub · DEV · PROD

**Satu aturan:** `master` di GitHub (`mashudizaini/ckdo-dashboard`) adalah satu-satunya sumber kebenaran.
Laptop, Claude Desktop, server DEV, dan server PROD semuanya **mengikuti** GitHub — tidak ada yang mengedit di jalur lain.

```
 VS Code / Claude Code ─┐
                        ├─► commit ─► GitHub master ─► DEV (cek) ─► PROD
 Claude Desktop ─► patch┘
```

---

## Kenapa perubahan bisa "kembali ke asal"

| Penyebab | Contoh nyata di repo ini |
|---|---|
| Mulai kerja dari salinan yang basi | 8 Okt: laptop tertinggal 9 commit dari GitHub |
| File utuh dari Claude Desktop disalin menimpa file di repo | Berkas itu dibuat dari snapshot lama; semua perubahan setelah snapshot ikut hilang |
| Pekerjaan tertinggal di branch/worktree yang tidak di-merge | 5 worktree lama di `.claude/worktrees/` |
| Edit langsung di server (scp, nano) | Bentrok saat `git pull`, lalu "dibereskan" dengan `stash`/`reset` → hilang |
| Pengaturan di luar git (Keycloak, `.env`, cron, DSM) | Tidak ikut git, tidak ikut dikembalikan, tidak tercatat |

---

## 1. Sebelum mulai — setiap kali, alat apa pun

```bash
cd D:/ckdo-dashboard-v2
git status          # harus bersih; kalau tidak, commit dulu yang tertinggal
git pull            # ambil yang terbaru dari GitHub
```

**Satu modul, satu alat dalam satu waktu.** Jangan mengedit modul yang sama di VS Code dan Claude Desktop secara paralel.

## 2. Kerja di VS Code / Claude Code

- Kerja langsung di folder `D:/ckdo-dashboard-v2` (branch `master`).
- Sebelum push perubahan frontend, wajib lolos:
  ```bash
  python scripts/check_imports.py
  ```
- Commit kecil per fitur, sebut file satu per satu:
  ```bash
  git add <file1> <file2>        # JANGAN git add -A
  git commit -m "feat(modul): apa yang berubah dan kenapa"
  git push
  ```

## 3. Kerja di Claude Desktop (akun lain, tanpa akses git)

1. Lakukan **langkah 1** dulu di laptop, lalu berikan ke Claude Desktop **berkas terbaru dari folder repo**, bukan salinan lama.
2. Minta hasilnya berupa **patch** (`git diff`/unified diff), **bukan berkas utuh**.
3. Simpan di `sumber/<nama-fitur>/` (folder ini tidak ikut git).
4. Pasang lewat VS Code:
   ```bash
   git pull
   git apply --check sumber/<nama-fitur>/<file>.patch   # uji dulu
   git apply sumber/<nama-fitur>/<file>.patch
   git diff                                             # baca sebelum commit
   ```
5. **Kalau `git apply --check` gagal, artinya patch dibuat dari kode basi.** Jangan dipaksa dan jangan menyalin berkas utuh. Ulangi pekerjaannya dengan berkas terbaru.
6. Commit dan push seperti langkah 2.

## 4. Deploy — selalu dari GitHub, DEV dulu

| | Host | Folder |
|---|---|---|
| DEV | `user@172.21.2.209` | `/opt/ckdo/ckdo-dashboard` |
| PROD | `dashboarduser@172.21.2.28` | `/home/dashboarduser/ckdo/ckdo-dashboard` |

```bash
ssh <host> "cd <folder> && git status --short && git pull --ff-only"
```

- Backend dan frontend reload sendiri (bind mount + `--reload` / Vite). Cek `docker logs ckdo_backend --tail 30`.
- Ada dependensi baru (`requirements.txt` / `package.json`) → `docker compose ... up -d --build`.
- Ada kolom/tabel baru → `backend/scripts/sync_schema.py` (dry-run dulu, lalu `--apply`).
- Mengubah `nginx.conf` → `docker compose up -d --force-recreate nginx` (reload saja tidak cukup).
- Buka halaman di DEV dan coba. Baru setelah itu jalankan perintah yang sama di PROD.

**Kalau server tidak bisa menjangkau GitHub** (`git pull` gagal/time out), kirim dari laptop lewat bundle. Hasilnya tetap commit yang identik, bukan salinan berkas:
```bash
git bundle create /tmp/up.bundle <commit-di-server>..master
scp /tmp/up.bundle <host>:/tmp/
ssh <host> "cd <folder> && git fetch /tmp/up.bundle master:refs/remotes/origin/master && git merge --ff-only origin/master"
```

## 5. Dilarang

- Mengedit berkas atau scp langsung ke server.
- `git stash` / `git reset --hard` / `git checkout -- .` di server tanpa memeriksa isinya dulu.
- `git push --force` ke `master`.
- Menyalin berkas utuh dari Claude Desktop ke repo.
- `git add -A` (ikut membawa `dist/`, `node_modules/`, berkas uji).

## 6. Pengaturan di luar git — catat setiap kali diubah

Keycloak (realm `ckdo`: SSO Session Idle 100 menit, access token 20 menit), `.env` server, cron di server DB, setelan Synology/FortiGate.
Semua itu **tidak ikut git**. Catat perubahannya (apa, nilai lama → baru, tanggal) di pesan commit terkait atau di `docs/`.

## 7. Cek cepat: semuanya sinkron?

```bash
bash scripts/sync_status.sh
```
Keempat baris (laptop, GitHub, DEV, PROD) harus menunjukkan commit yang sama, dan tidak ada server yang berstatus "ada perubahan lokal".

## 8. Bersih-bersih bulanan

```bash
git worktree list                     # worktree lama yang sudah di-merge → hapus
git branch --no-merged master         # branch yang belum masuk master → merge atau hapus
git cherry -v master <branch>         # "-" = isinya sudah ada di master, aman dihapus
```
