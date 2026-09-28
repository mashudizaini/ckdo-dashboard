# ebs-ce-fa – Kas/Bank & Aset Tetap (rekonsiliasi bank, aset tetap, penyusutan)

Deskripsi (manifest): Rekonsiliasi bank (mutasi rekening koran belum cocok, transaksi sistem belum ada di bank), daftar
aset tetap, nilai buku, dan penyusutan per periode.

## 1. Kapan dipakai
bank, rekening koran, bank statement, rekonsiliasi bank, belum rekon, outstanding check, setoran dalam perjalanan,
transfer antar bank, aset, aset tetap, fixed asset, penyusutan, depresiasi, nilai buku, NBV, CAPEX, CIP.

## 2. Tool
| Pertanyaan | Tool |
|---|---|
| Item belum rekon per rekening | ce_get_unreconciled(bank_account_name?, date_to?, side?, group_by="summary") |
| Daftar transaksi belum rekon | ce_get_unreconciled(..., group_by="detail") |
| Aset per kategori / lokasi / status | fa_get_assets(category?, location?, status?, group_by) |
| Satu aset | fa_get_assets(asset="nomor/tag/deskripsi", group_by="asset") |
| Penyusutan satu periode | fa_get_depreciation(period, category?, group_by="category" atau "asset") |
| Penyusutan periode sudah dijalankan? | gl_get_period_status(period, application="FA") — kolom deprn_run |

## 3. Definisi istilah
- side BANK = "belum rekon di sistem": baris rekening koran tanpa pasangan transaksi sistem.
- side SYSTEM = "belum muncul di bank": pembayaran AP (negotiable/issued), penerimaan AR (remitted/confirmed), dan
  transfer bank CE (created) yang belum cocok ke statement — outstanding check dan deposit in transit. Data 24 bulan.
- Tanda nilai: uang keluar negatif (pembayaran AP, debit bank), uang masuk positif.
- "Nilai buku" (NBV) = cost − akumulasi penyusutan. Status aset: Aktif, CIP, Retired, Fully reserved.

## 4. Aturan query
- Rekening bank disebut dengan nama rekening/bank, bukan nomor rekening (nomor tidak ada di mart).
- Selalu tampilkan statement_terakhir per rekening di ringkasan rekonsiliasi.
- Penyusutan per kategori dan per periode; aset per lokasi jika diminta. Nominal IDR penuh.

## 5. Jebakan praktisi
- Statement yang belum di-load membuat semua transaksi sistem sesudah tanggal statement terakhir terlihat "belum
  rekon"; bandingkan tanggal transaksi dengan statement_terakhir sebelum menyimpulkan.
- Jika hampir semua pembayaran/penerimaan sejak lama muncul di sisi SYSTEM, kemungkinan rekonsiliasi bank tidak
  dilakukan di Cash Management — sebutkan sebagai temuan, bukan sebagai selisih kas.
- Aset CIP belum disusutkan; pisahkan dari aset capitalized.
- Penyusutan periode yang belum dijalankan (Run Depreciation) belum ada; nilai periode berjalan bisa nol — cek
  deprn_run di gl_get_period_status(application="FA").
- Penyusutan FA suatu periode bisa lebih besar dari jurnal GL kategori "Depreciation": catch-up penyusutan aset yang
  ditambahkan mundur (tanggal mulai dipakai di periode lalu) masuk jurnal "Addition". Contoh JUL-26: FA
  Rp 1.655.056.248 vs jurnal Depreciation Rp 1.399.861.248 — sisanya ikut jurnal Addition.
- PO CAPEX → aset melalui Mass Additions; aset yang belum di-post dari Mass Additions belum muncul di register.

## 6. Tanya balik jika
- Rekening bank tidak disebut dan ada lebih dari satu rekening (tampilkan ringkasan semua rekening dulu jika user
  minta gambaran umum).
- "Nilai aset" — harga perolehan (cost) atau nilai buku (NBV)?

## 7. Contoh
- Transaksi bank BCA yang belum rekon sampai 31-08-2026 → ce_get_unreconciled(bank_account_name="BCA", date_to="2026-08-31")
- Penyusutan per kategori AUG-26 → fa_get_depreciation(period="AUG-26")
- Nilai buku aset per lokasi → fa_get_assets(group_by="location")
