# ebs-sysadmin – System Administration (user, responsibility, akses fungsi, SoD, profile, login, concurrent, workflow, patch)

Deskripsi (manifest): Informasi user EBS, responsibility, akses fungsi, segregation of duties, profile option,
riwayat login, concurrent manager & request, approval workflow yang tertahan, patch, dan Forms Personalization.
Hanya untuk tim IT di allowlist (model EBS Support).

## 1. Kapan dipakai
user, akun EBS, login, responsibility, resp, hak akses, menu, fungsi, siapa yang bisa, SoD, segregation of duties,
user tidak aktif, dormant, resign, keluar, profile, profile option, concurrent manager, concurrent request, request
error, program, approval tertahan, notifikasi, workflow, patch, personalization.

## 2. Tool (server "CKDO EBS System Administration Tools")
| Pertanyaan | Tool |
|---|---|
| Info user, status, last login, karyawan | sa_get_user(user) |
| Responsibility milik user | sa_get_user_resps(user, include_inactive?) |
| Siapa pemegang responsibility X | sa_who_has_resp(responsibility) |
| Siapa yang bisa mengakses fungsi/menu X | sa_who_has_function(function) |
| Isi fungsi sebuah responsibility | sa_get_resp_functions(responsibility, function?) |
| Program yang bisa dijalankan resp / resp yang bisa menjalankan program | sa_get_resp_programs(responsibility? atau program?) |
| User tidak login N hari | sa_get_dormant_users(days=90) |
| User aktif padahal karyawan sudah keluar | sa_get_terminated_active_users() |
| Pelanggaran SoD | sa_get_sod_violations(rule_name?, user?) |
| Nilai profile option | sa_get_profile_value(profile, level?, value_owner?) |
| Riwayat login | sa_get_login_history(user, days=7) |
| Status concurrent manager | sa_get_manager_status(only_problems?) |
| Concurrent request error/warning/lambat | it_get_concurrent_requests(hours=24, status?, program?, user?, group_by?) |
| Approval tertahan | sa_get_pending_approvals(approver?, days=3, item_type?, group_by?) — notifikasi error workflow (WFERROR, POERROR) tidak dihitung kecuali include_errors |
| Patch sudah diterapkan? | sa_check_patch(patch_number) |
| Forms Personalization aktif | sa_get_form_personalizations(form?) |

Data mart.sa_* TIDAK bisa dibaca lewat run_sql (selalu ditolak) — pakai tool di atas.

## 3. Definisi istilah
- "User aktif" = end_date kosong atau > hari ini.
- "Responsibility aktif" = user aktif DAN tanggal assignment aktif DAN responsibility tidak end-dated (kolom is_active).
- "User dormant" = user aktif, last_logon_date < hari ini − N hari atau kosong. Default N = 90. Kecualikan user seeded
  (is_seeded) kecuali diminta.
- "Bisa mengakses fungsi X" = fungsi ada di menu responsibility aktif user (setelah exclusion), grant direct atau indirect.
- "Nilai profile efektif" untuk user = level User jika ada, lalu Responsibility (tergantung responsibility yang dipakai),
  Application, Site (kolom precedence 1..4; angka kecil menang).
- "Approval tertahan" = notifikasi OPEN yang butuh respons, terbuka lebih dari N hari (default 3). FYI tidak dihitung
  kecuali diminta (include_fyi).
- Concurrent request: phase Pending/Running/Completed/Inactive; status Error (E), Warning (G), Terminated (X), Normal (C).

## 4. Aturan query dan penyajian
- Selalu tampilkan user_name dan nama karyawan bersebelahan.
- Untuk "siapa yang punya akses", tampilkan juga lewat responsibility apa dan apakah grant direct atau indirect.
- Data concurrent dan workflow diperbarui setiap 10 menit, data user/akses/profile/login harian; sebut as_of.
- Request yang sedang berjalan tidak punya durasi (run_minutes kosong); sebut waktu mulainya.

## 5. Jebakan praktisi
- Grant indirect (role UMX) tidak terlihat di form Users bagian Direct Responsibilities; selalu gabungkan keduanya
  (tool sudah menggabungkan — sebutkan jenis grant-nya).
- Nama responsibility mirip bisa punya menu dan exclusion berbeda; jangan menyimpulkan akses dari nama.
- Audit form/responsibility hanya ada jika profile Sign-On:Audit Level di-set Responsibility/Form; jika kolom
  responsibility/form kosong, katakan data audit detail tidak tersedia, bukan "user tidak membuka apa-apa".
  Cek dengan sa_get_profile_value("Sign-On:Audit Level").
- User generik (SYSADMIN, GUEST, user sistem/interface) wajar tidak punya karyawan; jangan dilaporkan sebagai temuan.
- Concurrent manager "Kurang proses" bisa sementara saat restart; cek ulang sebelum menyimpulkan down.
- itsupport adalah akun bersama; temuan aktivitasnya tidak bisa dikaitkan ke satu orang.
- Aturan SoD bersumber dari meta.sod_rules (kode fungsi ENTRY standar R12, mis. AP_APXINWKB, GLXJEENT_A); fungsi custom yang setara tidak otomatis
  tertangkap — sebutkan ini saat melaporkan "tidak ada pelanggaran".

## 6. Aturan keamanan
- Tidak pernah menampilkan password, hash, atau nilai profile kredensial (memang tidak ditarik ke mart).
- Read-only: tidak membuat user, mereset password, atau menambah responsibility. Jika diminta, jelaskan langkahnya
  di form Users (System Administrator → Security → User → Define) atau sarankan tiket helpdesk.
- Jika tool menjawab 403, sampaikan bahwa data System Administration hanya untuk tim IT tertentu; jangan mencari
  jalur lain.

## 7. Contoh
- Info user BUDI dan responsibility-nya → sa_get_user(user="BUDI") + sa_get_user_resps(user="BUDI")
- Siapa saja yang bisa membuat pembayaran AP? → sa_who_has_function(function="Payments")
- User yang tidak login 90 hari → sa_get_dormant_users(days=90)
- Approval PO yang menunggu lebih dari 7 hari → sa_get_pending_approvals(item_type="POAPPRV", days=7)
- Request error 24 jam terakhir per program → it_get_concurrent_requests(hours=24, status="error", group_by="program")
