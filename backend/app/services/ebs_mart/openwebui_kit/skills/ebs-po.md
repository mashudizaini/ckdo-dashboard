# PO – Purchase Order & Purchase Requisition

## Kapan dipakai
PO, purchase order, pesanan pembelian, PO outstanding, belum datang, belum diterima, terlambat kirim,
sudah ditagih belum, 3-way match, uninvoiced receipts, penerimaan belum ditagih, PR, requisition,
permintaan pembelian, PR belum jadi PO

## Mart
- mart.po_outstanding: 1 baris = shipment PO approved yang belum diterima penuh.
  Kolom kunci: po_number, vendor_name, item_code, item_desc, uom, qty_ordered, qty_received,
  qty_outstanding, amount_outstanding_idr, due_date, days_late, delivery_status.
- mart.po_receipt_vs_invoice: 1 baris = distribusi PO dengan qty order / terima / tagih.
  Kolom kunci: po_number, qty_ordered, qty_received, qty_billed, qty_received_not_billed,
  amount_received_not_billed_idr, match_type, match_status, last_invoice_num.
- mart.pr_pending: 1 baris = baris PR approved yang belum dibuatkan PO.
  Kolom kunci: pr_number, preparer, requester, item_desc, quantity, uom, days_waiting, amount_idr.

## Intent tool (utamakan)
- PO yang belum datang / terlambat → get_po_outstanding (late_only, group_by: none | supplier)
- "PO X sudah ditagih belum?", uninvoiced receipts → get_po_match_status
  (po_number; status 'Diterima, belum ditagih penuh' untuk uninvoiced; group_by: none | supplier | status)
- PR yang belum jadi PO → get_pr_pending (person, min_days_waiting, group_by: none | preparer)

## Aturan bisnis
- Outstanding = qty order − qty batal − qty diterima, di level shipment. Shipment CLOSED / FINALLY CLOSED /
  CLOSED FOR RECEIVING tidak dihitung outstanding walaupun kurang terima.
- Tanggal acuan kirim (due_date) = promised date, kalau kosong need-by date.
- Nilai *_idr: harga × kurs PO (rate di PO, kalau kosong kurs Corporate saat PO dibuat). Rupiah penuh.
- 3-way match: qty_received dari distribusi (sudah didelivery ke tujuan); qty_billed = qty yang dicocokkan AP.
  Pada 2-way (tanpa penerimaan) tagihan > penerimaan itu normal, bukan masalah.
- PR pending hanya PR pembelian (sumber VENDOR), approved, tidak batal/closed. PR data uji (user ELLVIN, AFNI)
  dikecualikan, sama seperti laporan Open PR di dashboard.
- Setiap qty wajib bersama uom.

## Jebakan umum
- Satu nomor PO bisa punya banyak baris/shipment/distribusi: jumlahkan per PO bila ditanya total per PO.
- Blanket PO: bedakan dengan release_num.
- Invoice yang dicocokkan ke PO lihat last_invoice_num/invoice_count; untuk status bayar invoice itu pakai skill ebs-ap.

## Contoh (golden queries)
Q: PO outstanding per supplier
SQL: SELECT vendor_name, COUNT(DISTINCT po_number) jml_po, SUM(amount_outstanding_idr) outstanding_idr
     FROM mart.po_outstanding GROUP BY vendor_name ORDER BY 3 DESC;

Q: penerimaan yang belum ditagih per supplier
SQL: SELECT vendor_name, SUM(amount_received_not_billed_idr) belum_ditagih_idr
     FROM mart.po_receipt_vs_invoice WHERE qty_received_not_billed > 0
     GROUP BY vendor_name ORDER BY 2 DESC;
