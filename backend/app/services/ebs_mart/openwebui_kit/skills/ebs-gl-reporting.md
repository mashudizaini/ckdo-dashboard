# GL – Laporan Keuangan, Trial Balance & Jurnal

## Kapan dipakai
laba rugi, P&L, profit, rugi, pendapatan, beban, biaya operasional, opex, gross profit, trial balance, neraca saldo,
saldo akun, neraca, kas & bank, jurnal, posting, jurnal dari invoice mana, akun biaya listrik, biaya per departemen

## Mart
- mart.pl_monthly: 1 baris = pos laba rugi × departemen × periode. Kolom: section, line, dept_desc, amount.
- mart.gl_trial_balance: 1 baris = akun × departemen × periode. begin_balance, period_dr, period_cr, end_balance
  (debit positif) dan end_balance_fs (sesuai penyajian laporan), statement BS/PL, fs_line.
- mart.gl_journal_detail: 1 baris = baris jurnal posted 13 bulan terakhir, dengan je_source, je_category,
  debit_idr, credit_idr, dan transaksi subledger asal (subledger_entity, subledger_txn_number).

## Intent tool (utamakan)
- Laba rugi, gross profit, laba bersih, perbandingan tahun lalu → get_pl (period YYYY / YYYY-MM, ytd,
  compare_prior_year, department, level line | section)
- Saldo akun, trial balance, pos neraca → get_trial_balance (period satu bulan; group_by account | fs_line | department)
- Jurnal, asal jurnal, jurnal dari invoice X → get_gl_journals (subledger_txn untuk nomor invoice/receipt)

## Aturan bisnis
- Ledger 2022, IDR fungsional, kalender CKDO_GL_CAL (periode JUL-26; ADJ-xx = periode penyesuaian).
- Mapping akun ke pos laba rugi dan neraca SAMA dengan laporan Financial Statement dashboard (sumbernya modul
  itu). Laba setelah pajak = (penjualan bersih − HPP) − beban operasional + pendapatan/beban lain + pajak.
- Akun di rentang laba rugi yang belum terpetakan (UNMAPPED) tidak masuk total, sama seperti laporan dashboard —
  sebutkan bila ada.
- get_pl sudah memberi baris 'TOTAL <section>' per section dan subtotal laporan (NET SALES, GROSS PROFIT, dst.).
  Dengan compare_prior_year ada juga selisih_idr dan perubahan_pct. Pakai angka itu apa adanya — JANGAN
  menjumlah, mengurangi, atau membulatkan sendiri, dan jangan menambah penjelasan penyebab yang tidak ada di data.
- Tahun penuh (period = YYYY) termasuk periode penyesuaian; YTD (ytd = true) tidak.
- Nilai dalam Rupiah penuh.
- Neraca (get_trial_balance group_by fs_line, tanpa filter akun/departemen): baris RETAINED EARNINGS - CURRENT
  YEAR dan OTHER COMPREHENSIVE INCOME - CURRENT YEAR diisi laba setelah pajak / OCI YTD tahun itu (belum ditutup
  di GL) — sama dengan laporan Financial Statement dashboard. Per akun (group_by account) saldo akun itu masih 0
  sampai tutup buku; jelaskan bila ditanya.

## Jebakan umum
- "Biaya listrik" dll.: cari dengan nama akun di parameter account (cocok sebagian) — jangan menebak nomor akun.
- Detail jurnal hanya 13 bulan terakhir; untuk periode lebih lama pakai trial balance / laba rugi.
- Satu baris jurnal ringkasan bisa berasal dari banyak transaksi subledger (subledger_txn_count > 1).

## Contoh (golden queries)
Q: laba rugi per bagian tahun ini
SQL: SELECT section, SUM(amount) nilai_idr FROM mart.pl_monthly
     WHERE period_year = EXTRACT(YEAR FROM CURRENT_DATE) AND section <> 'UNMAPPED'
     GROUP BY section, section_order ORDER BY section_order;
