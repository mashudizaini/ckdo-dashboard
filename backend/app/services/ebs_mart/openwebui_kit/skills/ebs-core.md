# ebs-core – Dasar Oracle EBS CKDO (organisasi, alur dokumen lintas modul, istilah, konvensi periode)

Deskripsi (manifest): Glosarium dan alur dokumen Oracle EBS CKDO lintas modul (PR, PO, GRN, invoice, SO, delivery,
batch, jurnal, periode); muat untuk setiap pertanyaan data EBS.

## 1. Organisasi & konstanta
- Operating Unit (OU) org_id 81: PO, AP, OM, AR, CE memakai ini.
- Ledger 2022, IDR, COA 50388: Company-LOB-Department-Account-Future1-Future2 (contoh 10-00-00-511111-000-000).
  Akun natural = segment4 (6 digit); departemen = segment3.
- Inventory/manufacturing org 121 (OPM, process org). Item, stok, batch, dan biaya produk dilihat di org ini.
- Periode GL: kalender CKDO_GL_CAL, nama MON-YY (JUL-26). Periode inventory (org 121) dan periode costing OPM
  (CKDO_PMAC) terpisah dari periode GL dan bisa beda status — lihat gl_get_period_status.

## 2. Alur dokumen
Procure-to-Pay:
  PR (requisition) → PO (header/line/shipment/distribution) → Receipt/GRN (RECEIVE → DELIVER) → AP invoice (match ke
  PO/receipt) → Validasi → Payment → Accounting (SLA) → GL
Order-to-Cash:
  SO → Book → Pick release → Ship confirm (delivery) → AutoInvoice (AR invoice) → Receipt → Apply → Accounting → GL
Produksi (OPM):
  Recipe/formula → Batch (Pending → WIP → Completed → Closed) → konsumsi bahan (ingredient) & hasil (product) →
  Actual Cost Process (PMAC) → Subledger Accounting OPM → GL

Tool per tahap:
| Tahap | Tool |
|---|---|
| PR belum PO | get_pr_pending |
| PO belum diterima | get_po_outstanding |
| Sudah diterima / sudah ditagih | get_po_match_status, po_get_uninvoiced_receipts |
| Hutang, hold, pembayaran | get_ap_aging, get_ap_open_invoices, get_ap_holds, get_ap_payments |
| SO belum kirim / status kirim | get_so_backlog, get_so_shipment_status |
| Sudah kirim belum invoice | so_get_shipped_not_invoiced, ar_get_autoinvoice_errors |
| Piutang & penerimaan | get_ar_aging, get_ar_open_invoices, get_ar_receipts, ar_get_unapplied_receipts |
| Stok, lot, mutasi, nilai | get_stock_onhand, get_expiring_lots, get_stock_movement, get_inventory_value |
| Batch produksi | get_batch_status, get_batch_yield, get_batch_material_usage, opm_get_open_batches |
| GL | get_trial_balance, get_pl, get_gl_journals, gl_get_period_status, gl_get_subledger_gap |
| Bank & aset | ce_get_unreconciled, fa_get_assets, fa_get_depreciation |

## 3. Istilah yang sering tertukar
- "Tanggal invoice" (invoice_date) ≠ "GL date" (tanggal akuntansi) ≠ "due date".
- "Nilai PO" = qty × harga di line/shipment; "sudah diterima" & "sudah ditagih" ada di level shipment/distribution,
  bukan header.
- "Entered amount" = mata uang dokumen; "accounted amount" = IDR. Agregasi = IDR (kolom *_idr).
- "Open" di PO = belum closed; di SO = open_flag Y; di AR/AP = sisa saldo ≠ 0; di periode = status Open. Selalu
  pastikan "open" yang mana.
- "Stok" = on-hand qty. Nilai stok org 121 = qty × biaya OPM (PMAC), bukan standard cost.
- "Supplier" (AP_SUPPLIERS) vs "supplier site" (alamat/term pembayaran). "Customer" = account (nomor) vs party (nama)
  vs site (bill-to/ship-to).

## 4. Aturan query umum
- Periode relatif: "bulan ini" = periode berjalan menurut tanggal hari ini (WIB); "bulan lalu" = periode sebelumnya.
  Sebutkan nama periode yang dipakai di jawaban.
- Nama mirip (supplier/customer/item): jika hasil tool memuat beberapa nama yang cocok, tanyakan user memilih yang mana.
- Pertanyaan lintas modul (mis. "PO ini sudah dibayar?") dijawab berurutan mengikuti alur dokumen di atas, satu tool
  per tahap.

## 5. Jebakan praktisi
- Data per waktu ETL, bukan real-time. Transaksi hari ini bisa belum masuk; cek get_data_freshness jika user bilang
  "kok belum ada".
- Dokumen cancelled tetap ada di tabel EBS; mart sudah mengecualikan kecuali disebut.
- Nomor dokumen bisa sama antar tipe (nomor PO = nomor SO berbeda objek). Selalu sebut tipe dokumen.

## 6. Tanya balik jika
- Periode tidak disebut dan pertanyaan tentang mutasi/nilai (bukan saldo saat ini).
- User menyebut "nilai" tanpa jelas qty atau rupiah.
