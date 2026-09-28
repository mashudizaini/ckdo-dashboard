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
| PR belum PO | pr_get_pending |
| PO belum diterima / detail PO / menunggu approval | po_get_outstanding, po_get_document, po_get_pending_approval |
| Sudah diterima / sudah ditagih | po_get_match_status, po_get_uninvoiced_receipts |
| Hutang, hold, pembayaran | ap_get_aging, ap_get_open_invoices, ap_get_invoice, ap_get_holds, ap_get_payments, ap_get_due_forecast, ap_get_withholding |
| SO belum kirim / status kirim / detail SO / hold | so_get_backlog, so_get_shipment_status, so_get_order, so_get_holds |
| Sudah kirim belum invoice | so_get_shipped_not_invoiced, ar_get_autoinvoice_errors |
| Piutang & penerimaan | ar_get_aging, ar_get_customer_balance, ar_get_open_invoices, ar_get_receipts, ar_get_unapplied_receipts |
| Stok, lot, mutasi, nilai | inv_get_onhand, inv_get_expiring_lots, inv_get_movements, inv_get_stock_card, inv_get_slow_moving, inv_get_valuation |
| Batch produksi & biaya | opm_get_batch, opm_get_yield, opm_get_material_usage, opm_get_open_batches, opm_get_item_cost |
| GL | gl_get_trial_balance, gl_get_account_movement, gl_get_pl, gl_get_journals, gl_get_budget_vs_actual, gl_get_period_status, gl_get_subledger_gap |
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
- Nama mirip (supplier/customer/item/akun): panggil lookup_master(text, type) dulu; jika >1 kandidat, tanyakan user
  memilih yang mana, lalu pakai kode persisnya di tool berikutnya.
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
