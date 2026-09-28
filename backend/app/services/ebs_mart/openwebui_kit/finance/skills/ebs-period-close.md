# ebs-period-close – Checklist Tutup Buku (hambatan closing bulanan lintas modul)

Deskripsi (manifest): Status dan hambatan tutup buku bulanan lintas modul (PO, AP, OM/AR, Inventory, OPM costing, Cash,
Fixed Assets, GL) untuk periode tertentu.

## 1. Kapan dipakai
closing, tutup buku, month end, tutup periode, siap closing, apa yang belum, hambatan closing, buka periode, status
periode.

## 2. Cara kerja
1. Tetapkan periode (tanya jika tidak disebut; default periode lalu).
2. gl_get_period_status(period) — tampilkan status tiap aplikasi (GL, AP, AR, PO, INV, OPM, FA).
3. Jalankan pemeriksaan berurutan:
   a. PO: po_get_uninvoiced_receipts(as_of_period=period) — dasar accrual
   b. AP: get_ap_holds, gl_get_subledger_gap(period, application="AP")
   c. OM/AR: so_get_shipped_not_invoiced, ar_get_autoinvoice_errors(group_by="error"), ar_get_unapplied_receipts,
      gl_get_subledger_gap(period, application="AR")
   d. INV: get_stock_onhand (qty negatif), get_expiring_lots(include_expired=true) untuk lot sudah expired di GOOD
   e. OPM: opm_get_open_batches, status periode costing (OPM) dan INV dari langkah 2
   f. CE/FA: ce_get_unreconciled(date_to=akhir periode), gl_get_period_status(application="FA") → deprn_run,
      fa_get_depreciation(period)
   g. GL: gl_get_subledger_gap(period) untuk semua aplikasi (termasuk "Jurnal GL belum posting")
   Untuk tiap langkah laporkan: jumlah item, nilai IDR, 5 contoh teratas.
4. Ringkas sebagai checklist: ✅ siap / ⚠️ perlu tindakan / ❌ penghalang, dengan pemilik tindakan (Purchasing, AP, AR,
   Gudang, Produksi, Costing, GL, IT).

## 3. Aturan
- Jangan menyatakan "siap closing" jika ada satu saja penghalang ❌.
- Penghalang ❌ (umum): event belum di-account / accounting error / final belum transfer untuk periode itu, jurnal GL
  belum posting, AutoInvoice error untuk barang yang sudah dikirim, penyusutan FA belum dijalankan.
- Perlu tindakan ⚠️ (umum): receipt belum ditagih (accrual), invoice di-hold, receipt unapplied, batch lama belum
  Closed, item bank belum rekon.
- Urutan closing standar: PO/AP → OM/AR → INV/OPM → CE/FA → GL.
- Status periode inventory dan costing OPM dibaca saja; menutupnya berdampak biaya yang tidak bisa dibalik. Selalu
  sebutkan ini jika user bertanya "boleh ditutup?".

## 4. Jebakan praktisi
- Invoice/payment unaccounted adalah penyebab paling umum selisih AP vs GL.
- AutoInvoice error untuk SO ekspor sering karena nomor transaksi/kurs; ini menghalangi pengakuan pendapatan periode.
- po_get_uninvoiced_receipts memakai qty diterima/ditagih SAAT INI (bukan posisi historis akhir periode); sebutkan
  ini untuk periode yang sudah lewat.
- Encumbrance PO pada periode yang sudah ditutup bisa menghalangi cancel PO bulan berikutnya.
- Actual Cost Process harus dijalankan ulang setelah invoice AP susulan untuk item bahan baku; biaya belum final
  sebelum itu.
- Data closing (status periode, SLA, AutoInvoice, bank) diperbarui tiap jam 06:15–20:15; aset tetap harian. Sebut as_of.

## 5. Tanya balik jika
- Periode tidak disebut.
- User meminta "tutup periode" — jelaskan bahwa asisten hanya membaca data, lalu tampilkan checklist.
