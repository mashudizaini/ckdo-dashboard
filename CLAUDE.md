# CKDO Dashboard v2 — aturan kerja

Ikuti `docs/SOP_SINKRONISASI.md`. Ringkasnya:

- `master` di GitHub adalah sumber kebenaran. Mulai dengan `git status` (harus bersih) lalu `git pull`.
- Jangan pernah mengedit atau scp berkas langsung ke server DEV/PROD. Deploy hanya lewat `git pull --ff-only` di server (DEV dulu, lalu PROD), atau git bundle bila server tidak bisa menjangkau GitHub.
- Hasil dari Claude Desktop dipasang sebagai patch (`git apply --check` dulu), tidak pernah sebagai berkas utuh.
- `git add <file>` satu per satu, bukan `git add -A`. Tidak ada `push --force`, dan tidak ada `stash`/`reset` di server tanpa memeriksa isinya.
- Sebelum push perubahan frontend: `python scripts/check_imports.py`.
- Pengaturan di luar git (Keycloak realm, `.env`, cron server DB) dicatat setiap kali diubah.
