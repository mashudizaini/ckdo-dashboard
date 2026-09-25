# AR – Piutang Usaha & Penerimaan Kas

## Kapan dipakai
piutang, AR, receivable, tagihan ke customer, aging piutang, jatuh tempo customer, telat bayar customer,
penerimaan kas, pembayaran dari customer, cash in, receipt, unapplied, on account, pelunasan

## Mart
- mart.ar_aging: 1 baris = jadwal piutang yang masih open (INV, DM, CM).
  Kolom kunci: customer_name, trx_number, class, due_date, days_overdue, aging_bucket (+ aging_bucket_order),
  currency_code, amount_remaining_entered, amount_remaining_idr, so_number.
- mart.ar_receipt: 1 baris = penerimaan × status aplikasi × invoice yang dilunasi.
  Kolom kunci: receipt_number, receipt_date, customer_name, application_status, applied_invoice_num, amount_idr.

## Intent tool (utamakan)
- Aging piutang per customer / per bucket → get_ar_aging (group_by: customer | bucket | customer_bucket)
- Invoice customer belum lunas, jatuh tempo minggu ini → get_ar_open_invoices
- Penerimaan kas, siapa bayar invoice apa, unapplied → get_ar_receipts (group_by: none | customer | month)

## Aturan bisnis
- Populasi ar_aging sama dengan laporan AR Outstanding dashboard: kelas INV/DM/CM, status OP, invoice
  setelah 31-12-2021 (sebelumnya dianggap lunas — data aplikasi lama tidak lengkap).
- amount_remaining_idr memakai kurs Corporate TERBARU (fx_rate_used, fx_rate_date), bukan kurs invoice —
  sebutkan ini untuk piutang valas. amount_remaining_idr_invoice_rate tersedia sebagai pembanding.
- Credit memo (class CM) bernilai negatif dan mengurangi total, sama seperti laporan dashboard.
- Penerimaan: jumlahkan amount_idr (per baris aplikasi), JANGAN receipt_amount_idr — itu total penerimaan
  yang diulang di setiap baris. Penerimaan yang di-reverse dikecualikan kecuali diminta (include_reversed).
- UNAPP = uang sudah masuk tetapi belum dicocokkan ke invoice mana pun.

## Jebakan umum
- "Customer X sudah bayar belum?" → cek dua sisi: sisa di ar_aging DAN penerimaan di ar_receipt.
- Nama customer dicocokkan sebagian; bila beberapa customer mirip, tanyakan yang dimaksud.
- Piutang dan penjualan berbeda: penjualan (omzet) pakai skill ebs-om / get_sales_by_customer.

## Contoh (golden queries)
Q: total piutang per aging bucket
SQL: SELECT aging_bucket, COUNT(*) jml_invoice, SUM(amount_remaining_idr) total_idr
     FROM mart.ar_aging GROUP BY aging_bucket, aging_bucket_order ORDER BY aging_bucket_order;
