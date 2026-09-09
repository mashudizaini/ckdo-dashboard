# Panduan Git — Kerja dari VS Code + Claude Desktop

Dokumen ini untuk satu masalah spesifik: dashboard ini dikerjakan dari **dua sisi**
— VS Code di laptop, dan Claude Desktop — dan keduanya harus tetap sinkron.

**Aturan tunggal yang membuat semuanya bekerja:**

> `master` di GitHub adalah satu-satunya sumber kebenaran.
> VS Code, Claude Desktop, dan dev server semuanya bertemu di sana.

Kalau ragu, kembalikan semua ke `master`, lalu mulai lagi dari sana.

---

## Kenapa ada branch `claude/*`?

Claude Desktop tidak mengedit folder kerja Anda. Ia membuat **git worktree** —
salinan repo yang terisolasi:

```
D:\ckdo-dashboard-v2\                        <- folder yang dibuka VS Code
└── .claude\worktrees\
    └── nama-modul-abc123\                   <- Claude bekerja di sini
```

Konsekuensinya, dan ini penting:

- Hasil kerja Claude **tidak otomatis muncul** di VS Code.
- Kalau Claude bilang "selesai", artinya **kode siap** — bukan sudah ter-deploy.
- Jembatannya cuma satu: Git. Commit di worktree → merge ke master → pull di VS Code.

Kalau branch `claude/*` tidak pernah di-merge dan VS Code tidak pernah dikembalikan
ke `master`, kedua sisi pelan-pelan berpisah. Itu penyebab desync yang paling sering.

---

## A. Merge Lokal (cepat, untuk kerjaan sendiri)

Dipakai kalau Anda yakin dengan perubahannya dan tidak butuh jejak review.

### A1. Commit hasil kerja Claude, dari dalam worktree

```
cd "D:/ckdo-dashboard-v2/.claude/worktrees/<nama-worktree>"
git status
git add <daftar file>
git commit -m "pesan yang jelas"
git push -u origin <nama-branch>
```

Sebutkan file satu per satu. **Jangan `git add -A`** — di worktree sering ada file
sisa build (`dist/`, `node_modules/`, file test) yang tidak boleh ikut.

### A2. Pindah ke master di folder VS Code

```
cd "D:/ckdo-dashboard-v2"
git status
git checkout master
git pull
```

`git status` di langkah ini wajib. Kalau ada perubahan yang belum di-commit,
**berhenti dulu** dan commit — jangan pindah branch sambil membawa perubahan.

### A3. Merge branch-nya ke master

```
git merge <nama-branch>
git push
```

Yang Anda harapkan: `Fast-forward` atau `Merge made by the 'ort' strategy`.
Kalau muncul `CONFLICT`, lihat bagian **Kalau kena conflict** di bawah.

### A4. Bersihkan (opsional, setelah yakin merge-nya benar)

```
git worktree remove .claude/worktrees/<nama-worktree>
git branch -d <nama-branch>
git push origin --delete <nama-branch>
```

---

## B. Merge lewat Pull Request di GitHub

Dipakai kalau perubahannya besar, menyentuh banyak modul, atau Anda ingin membacanya
lagi dengan kepala dingin sebelum masuk `master`.

### B1. Commit + push branch-nya

Sama persis dengan **A1** di atas. Sampai `git push`, lalu berhenti — jangan merge.

### B2. Buka PR di GitHub

1. Buka https://github.com/mashudizaini/ckdo-dashboard
2. GitHub biasanya menampilkan banner **"Compare & pull request"** untuk branch yang
   baru saja di-push. Klik itu.
   Kalau bannernya tidak muncul: tab **Pull requests** → **New pull request**.
3. Pastikan arahnya benar: `base: master` ← `compare: <nama-branch>`.
   **Arah ini sering tertukar.** `base` adalah tujuan.
4. Isi judul dan penjelasan singkat: apa yang berubah, dan apa yang perlu dites.
5. **Create pull request**.

### B3. Review

Buka tab **Files changed**. Cek jumlah file-nya masuk akal, dan tidak ada file yang
tidak Anda kenali (file build, file rahasia, file dari modul lain).

### B4. Merge

Klik **Merge pull request** → **Confirm merge**. Lalu **Delete branch** kalau ditawarkan.

### B5. Tarik hasilnya ke laptop

```
cd "D:/ckdo-dashboard-v2"
git checkout master
git pull
```

Langkah ini **wajib** dan paling sering terlupa. Merge di GitHub tidak mengubah
apa pun di laptop Anda sampai Anda `git pull`.

---

## C. Rutinitas sinkron VS Code

### Setiap kali MULAI kerja (di VS Code maupun sebelum membuka Claude Desktop)

```
cd "D:/ckdo-dashboard-v2"
git status
git checkout master
git pull
```

Kalau `git status` menunjukkan ada perubahan belum di-commit: commit dulu, baru pindah.

### Setiap kali SELESAI kerja di VS Code

```
git add <file yang Anda ubah>
git commit -m "pesan"
git push
```

### Setiap kali SELESAI sesi Claude Desktop

Langsung merge branch `claude/*` ke master (cara A atau B), lalu kembali ke master
di VS Code. **Jangan dibiarkan menggantung.** Satu branch menggantung masih bisa
diurus; tiga branch menggantung dari tiga sesi berbeda jauh lebih sulit.

### Cek cepat "saya di mana sekarang?"

```
git branch --show-current
```

Kalau jawabannya bukan `master` dan Anda tidak sedang sengaja mengerjakan sesuatu
di branch itu — kembali ke `master`.

---

## D. Deploy ke dev server

Deploy **selalu langkah terpisah**, dan hanya setelah `master` di GitHub sudah benar.

```
ssh user@172.21.2.209
cd /opt/ckdo/ckdo-dashboard
git rev-parse --abbrev-ref HEAD
git pull
```

Aturan keras: **jangan pernah `scp` file langsung ke server.** Repo di server itu
git clone yang ter-track; file yang di-scp menjadi perubahan lokal yang membuat
`git pull` berikutnya gagal.

Kalau `git pull` di server ditolak dengan *"local changes would be overwritten"*:
**jangan** langsung `git stash` / `git checkout --` / `git reset`. Lihat dulu
`git diff` file itu — bisa jadi ada kerjaan orang lain yang belum ter-capture.

### Kalau ada tabel database baru

`Base.metadata.create_all()` hanya jalan saat `ENVIRONMENT=development`. Di dev dan
production server, tabel baru **harus** dibuat manual dari script SQL-nya
(contoh: `backend/scripts/overtime_schema.sql`).

Dan `create_all` **tidak pernah** meng-`ALTER` tabel yang sudah ada. Kalau ada kolom
baru di tabel lama, kolom itu harus ditambahkan manual dengan `ALTER TABLE`.

---

## E. Kalau kena conflict

Conflict terjadi kalau file yang sama diubah di dua branch. Pencegahannya: jangan
mengedit file yang sama di VS Code sementara sesi Claude sedang berjalan.

Kalau sudah terjadi:

```
git status
```

File yang bertanda `both modified` adalah yang bermasalah. Buka di VS Code — VS Code
punya tampilan merge editor dengan tombol *Accept Current* / *Accept Incoming* /
*Accept Both*. Setelah semua selesai:

```
git add <file yang sudah dibereskan>
git commit
```

**Kalau bingung, batalkan saja** — merge bisa dibatalkan dengan aman, tidak ada yang hilang:

```
git merge --abort
```

---

## F. Yang tidak boleh dilakukan

| Jangan | Kenapa |
|---|---|
| `git add -A` di worktree Claude | Ikut menarik file build/test yang tidak seharusnya masuk repo |
| `scp` file ke server | Membuat perubahan lokal di server yang menggagalkan `git pull` berikutnya |
| `git stash` untuk "membereskan" pull yang gagal | Pernah menyebabkan kerjaan satu sesi hilang permanen |
| `git push --force` ke master | Menghapus commit orang lain tanpa peringatan |
| Membiarkan branch `claude/*` menggantung berhari-hari | Semakin lama, semakin besar kemungkinan conflict saat merge |
| Menganggap "Claude bilang selesai" = sudah live | Selesai artinya kode siap; merge dan deploy tetap langkah tersendiri |

---

## G. Status branch yang sedang ditahan

| Branch | Status | Catatan |
|---|---|---|
| `claude/hrga-emagazine-dynamic-yt7xag` | sudah di-push, **sengaja ditahan** | Jangan di-merge dulu sampai ada keputusan |

Perbarui tabel ini kalau ada branch lain yang ditahan, supaya tidak terlupa.
