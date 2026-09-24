# AP – Hutang Usaha

## Kapan dipakai
hutang, AP, payable, invoice supplier, tagihan supplier, jatuh tempo, aging, pembayaran,
pelunasan, transfer ke supplier, hold, invoice tertahan, PPh supplier

## Mart
- mart.ap_open_invoice: 1 baris = payment schedule (termin) invoice yang masih outstanding.
  Kolom kunci: vendor_name, invoice_num, due_date, days_overdue, aging_bucket (+ aging_bucket_order),
  currency_code, amount_remaining_entered, amount_remaining_idr.
- mart.ap_payment_history: 1 baris = satu pembayaran yang diaplikasikan ke satu invoice.
  Kolom kunci: payment_date, payment_number, payment_method, vendor_name, invoice_num, amount_idr.
- mart.ap_invoice_hold: 1 baris = hold aktif. Kolom kunci: hold_code, hold_reason, hold_date, days_on_hold.

## Intent tool (utamakan)
- Aging per supplier / per bucket → get_ap_aging (group_by: supplier | bucket | supplier_bucket)
- Daftar invoice belum lunas, jatuh tempo minggu ini → get_ap_open_invoices (due_from/due_to)
- Pembayaran minggu/bulan lalu, total per supplier → get_ap_payments (group_by: none | supplier | month)
- Invoice di-hold → get_ap_holds

## Aturan bisnis
- "Hutang" / "outstanding" = amount_remaining_idr <> 0 di mart.ap_open_invoice.
- Populasi mart sama dengan laporan AP Outstanding di dashboard: akun hutang 2121xx/2122xx saja,
  invoice setelah 31-12-2021, bukan cancelled, GL date tidak di masa depan.
- Aging pakai due_date, kecuali user minta berdasarkan invoice_date — tanyakan bila tidak jelas
  ("hutang bulan ini" bisa berarti GL date bulan ini ATAU jatuh tempo bulan ini).
- Total per supplier: GROUP BY vendor_num, vendor_name.
- Invoice valas: tampilkan amount_remaining_entered + currency_code DAN amount_remaining_idr.
- IDR = kurs invoice (bukan revaluasi akhir bulan). Sebutkan bila user bertanya soal kurs.

## Jebakan umum
- PPh (AWT) bukan hutang ke supplier; invoice AWT ke kantor pajak tidak masuk akun hutang dagang.
- Invoice cancelled sudah dikecualikan di mart.
- Prepayment yang belum di-apply muncul sebagai saldo negatif/terpisah (invoice_type = PREPAYMENT).
- Nama supplier dicocokkan sebagian: jika hasil memuat beberapa supplier mirip, tanyakan yang dimaksud.
- Hold dengan invoice_found = false adalah hold yatim: invoice-nya sudah tidak ada di Oracle
  (AP_INVOICES_ALL), jadi supplier dan nomor invoice memang kosong. Sebutkan begitu — jangan menebak
  penyebab lain — dan sarankan dibersihkan di EBS.

## Contoh (golden queries)
Q: hutang lewat jatuh tempo > 60 hari per supplier
SQL: SELECT vendor_name, SUM(amount_remaining_idr) total_idr
     FROM mart.ap_open_invoice WHERE days_overdue > 60
     GROUP BY vendor_name ORDER BY 2 DESC;

Q: total hutang per aging bucket
SQL: SELECT aging_bucket, COUNT(*) jml_invoice, SUM(amount_remaining_idr) total_idr
     FROM mart.ap_open_invoice GROUP BY aging_bucket, aging_bucket_order ORDER BY aging_bucket_order;
