"""
Seed content for meta.column_catalog and meta.golden_query.

Seeded with INSERT ... ON CONFLICT DO NOTHING (descriptions) so anything an
administrator edits in Setup > AI > EBS Data Mart survives every restart;
only data_type is kept in sync with the live view. The blueprint's weekly
improvement loop (section 11) adds synonyms and golden queries through that
screen, not here — this file is the starting point, not the source of truth.
"""

# (description_id, synonyms). Columns not listed still get a catalog row
# (with their data type) when the mart is built; they simply start without a
# description until someone writes one.
COLUMN_CATALOG: dict[str, dict[str, tuple[str, list[str]]]] = {
    "ap_open_invoice": {
        "invoice_id": ("ID internal invoice Oracle (kunci join)", []),
        "payment_num": ("Nomor jadwal pembayaran (termin) dalam satu invoice", ["termin", "cicilan"]),
        "vendor_num": ("Nomor supplier di Oracle", ["kode supplier", "vendor number"]),
        "vendor_name": ("Nama supplier", ["supplier", "vendor", "pemasok"]),
        "vendor_site_code": ("Kode site supplier", ["site supplier"]),
        "invoice_num": ("Nomor invoice supplier", ["no invoice", "nomor tagihan", "faktur"]),
        "invoice_type": ("Tipe invoice (STANDARD, CREDIT, PREPAYMENT, ...)", ["jenis invoice"]),
        "invoice_date": ("Tanggal invoice", ["tanggal tagihan"]),
        "gl_date": ("Tanggal GL / tanggal akuntansi invoice", ["tanggal posting", "GL date"]),
        "gl_period_name": ("Periode GL invoice, format JUL-26", ["periode", "bulan"]),
        "gl_period_start_date": ("Tanggal awal periode GL invoice", []),
        "due_date": ("Tanggal jatuh tempo jadwal pembayaran", ["jatuh tempo", "JT", "due date"]),
        "currency_code": ("Mata uang invoice", ["valas", "currency", "mata uang"]),
        "gross_amount_entered": ("Nilai bruto jadwal pembayaran dalam mata uang invoice", []),
        "amount_remaining_entered": ("Sisa hutang dalam mata uang invoice (untuk tampilan valas)", ["sisa valas"]),
        "amount_remaining_idr": ("Sisa hutang invoice dalam IDR — pakai kolom ini untuk menjumlah", ["hutang", "outstanding", "belum dibayar", "payable", "saldo hutang"]),
        "liability_account": ("Akun hutang (segment4 COA)", ["akun hutang", "COA"]),
        "days_overdue": ("Jumlah hari lewat jatuh tempo (negatif = belum jatuh tempo)", ["telat bayar", "overdue", "lewat JT", "umur hutang"]),
        "aging_bucket": ("Kelompok umur hutang: Current, 1-30, 31-60, 61-90, >90", ["aging", "umur hutang", "bucket"]),
        "aging_bucket_order": ("Urutan bucket aging (0 = Current ... 4 = >90) untuk ORDER BY", []),
        "description": ("Keterangan invoice", ["deskripsi"]),
    },
    "ap_payment_history": {
        "invoice_payment_id": ("ID baris aplikasi pembayaran (kunci)", []),
        "check_id": ("ID dokumen pembayaran", []),
        "payment_number": ("Nomor dokumen pembayaran / nomor cek", ["nomor bayar", "no pembayaran", "voucher"]),
        "payment_date": ("Tanggal dokumen pembayaran", ["tanggal bayar", "dibayar kapan"]),
        "accounting_date": ("Tanggal akuntansi pembayaran", []),
        "period_name": ("Periode akuntansi pembayaran, format JUL-26", ["periode", "bulan"]),
        "period_start_date": ("Tanggal awal periode pembayaran", []),
        "payment_method": ("Metode pembayaran (CHECK, EFT, WIRE, ...)", ["cara bayar", "transfer"]),
        "bank_account_name": ("Nama rekening bank pembayar (tanpa nomor rekening)", ["bank"]),
        "payment_status": ("Status dokumen pembayaran", []),
        "currency_code": ("Mata uang invoice", ["valas"]),
        "amount_entered": ("Nilai yang dibayarkan ke invoice dalam mata uang invoice", []),
        "amount_idr": ("Nilai yang dibayarkan dalam IDR — pakai untuk menjumlah", ["pembayaran", "dibayar", "nilai bayar"]),
        "invoice_id": ("ID invoice yang dibayar", []),
        "invoice_num": ("Nomor invoice yang dibayar", ["no invoice"]),
        "invoice_type": ("Tipe invoice", []),
        "invoice_date": ("Tanggal invoice", []),
        "vendor_num": ("Nomor supplier", []),
        "vendor_name": ("Nama supplier", ["supplier", "vendor"]),
        "vendor_site_code": ("Kode site supplier", []),
    },
    "ap_invoice_hold": {
        "hold_id": ("ID hold (kunci)", []),
        "invoice_id": ("ID invoice", []),
        "invoice_num": ("Nomor invoice yang di-hold", ["no invoice"]),
        "invoice_type": ("Tipe invoice", []),
        "invoice_date": ("Tanggal invoice", []),
        "vendor_num": ("Nomor supplier", []),
        "vendor_name": ("Nama supplier", ["supplier", "vendor"]),
        "currency_code": ("Mata uang invoice", []),
        "invoice_amount_entered": ("Nilai invoice dalam mata uang invoice", []),
        "invoice_amount_idr": ("Nilai invoice dalam IDR", ["nilai invoice"]),
        "hold_code": ("Kode hold (QTY REC, PRICE, ...)", ["alasan hold", "jenis hold"]),
        "hold_desc": ("Deskripsi kode hold", []),
        "hold_reason": ("Alasan hold yang tercatat", ["kenapa di-hold", "hold", "tertahan", "blokir"]),
        "hold_date": ("Tanggal hold dipasang", []),
        "days_on_hold": ("Sudah berapa hari invoice di-hold", ["lama hold"]),
    },
    "inv_onhand_lot": {
        "row_key": ("Kunci baris (item|subinventory|locator|lot)", []),
        "organization_code": ("Kode organisasi inventory", ["org", "gudang organisasi"]),
        "item_code": ("Kode item Oracle — cocokkan persis", ["kode barang", "item", "SKU"]),
        "item_desc": ("Nama/deskripsi item — cocokkan sebagian (ILIKE)", ["nama barang", "bahan", "material", "produk"]),
        "uom": ("Satuan stok (primary UOM) — selalu tampilkan bersama qty", ["satuan", "unit"]),
        "item_category": ("Kategori item dari category set CKDO Inventory", ["kategori", "jenis barang", "bahan baku", "kemasan", "FG"]),
        "subinventory_code": ("Kode subinventory (gudang)", ["gudang", "subinv", "lokasi gudang"]),
        "subinventory_desc": ("Deskripsi subinventory", []),
        "subinventory_type": ("Klasifikasi subinventory: GOOD, REJECT, QUARANTINE", ["stok bagus", "reject", "karantina", "quarantine"]),
        "locator": ("Locator / rak di dalam subinventory", ["rak", "bin", "lokasi"]),
        "lot_number": ("Nomor lot / batch bahan", ["lot", "batch number", "no batch"]),
        "lot_status": ("Status lot di Oracle", ["status lot", "release"]),
        "origination_date": ("Tanggal lot dibuat", []),
        "expiration_date": ("Tanggal kedaluwarsa lot", ["ED", "expired date", "tanggal kadaluarsa"]),
        "days_to_expiry": ("Sisa hari sampai lot kedaluwarsa (negatif = sudah expired)", ["ED", "expired", "kadaluarsa", "mendekati expired"]),
        "expiry_bucket": ("Kelompok ED: Expired, <=90 hari, 91-180 hari, >180 hari, No ED", ["kelompok ED"]),
        "onhand_qty": ("Jumlah stok on-hand dalam satuan uom", ["stok", "qty", "persediaan", "sisa stok"]),
    },
    "inv_movement_daily": {
        "row_key": ("Kunci baris", []),
        "txn_date": ("Tanggal transaksi", ["tanggal mutasi"]),
        "period_name": ("Periode, format JUL-26", ["periode", "bulan"]),
        "period_start_date": ("Tanggal awal periode", []),
        "organization_code": ("Kode organisasi inventory", ["org"]),
        "item_code": ("Kode item Oracle", ["kode barang"]),
        "item_desc": ("Nama item", ["nama barang"]),
        "uom": ("Satuan transaksi", ["satuan"]),
        "subinventory_code": ("Subinventory", ["gudang"]),
        "transaction_type": ("Tipe transaksi inventory (PO Receipt, Move Order Issue, ...)", ["jenis transaksi", "mutasi"]),
        "qty_in": ("Jumlah masuk", ["masuk", "penerimaan", "in"]),
        "qty_out": ("Jumlah keluar (positif)", ["keluar", "pemakaian", "out", "issue"]),
        "net_qty": ("Mutasi bersih (masuk - keluar)", ["net"]),
        "txn_count": ("Jumlah transaksi", []),
    },
}

# Domain + mart-level synonyms, used by find_marts in addition to the column
# synonyms above.
MART_SYNONYMS: dict[str, list[str]] = {
    "ap_open_invoice": ["hutang", "AP", "payable", "hutang usaha", "aging hutang", "jatuh tempo", "outstanding supplier"],
    "ap_payment_history": ["pembayaran", "bayar", "payment", "pelunasan", "transfer supplier"],
    "ap_invoice_hold": ["hold", "tertahan", "blokir invoice", "invoice hold"],
    "inv_onhand_lot": ["stok", "persediaan", "on hand", "lot", "expired", "ED", "gudang", "kadaluarsa"],
    "inv_movement_daily": ["mutasi", "kartu stok", "pemakaian", "penerimaan barang", "transaksi stok", "keluar masuk"],
}

# (domain, question, sql). Blueprint 6.5 plus common phase-1 questions.
GOLDEN_QUERIES: list[tuple[str, str, str]] = [
    ("AP", "Hutang lewat jatuh tempo > 60 hari per supplier",
     "SELECT vendor_name, SUM(amount_remaining_idr) AS total_idr FROM mart.ap_open_invoice "
     "WHERE days_overdue > 60 GROUP BY vendor_name ORDER BY 2 DESC"),
    ("AP", "Total hutang per aging bucket",
     "SELECT aging_bucket, COUNT(*) AS jml_invoice, SUM(amount_remaining_idr) AS total_idr "
     "FROM mart.ap_open_invoice GROUP BY aging_bucket, aging_bucket_order ORDER BY aging_bucket_order"),
    ("AP", "10 supplier dengan hutang overdue terbesar",
     "SELECT vendor_name, SUM(amount_remaining_idr) AS overdue_idr FROM mart.ap_open_invoice "
     "WHERE days_overdue > 0 GROUP BY vendor_name ORDER BY 2 DESC LIMIT 10"),
    ("AP", "Hutang valas per mata uang",
     "SELECT currency_code, SUM(amount_remaining_entered) AS sisa_valas, SUM(amount_remaining_idr) AS sisa_idr "
     "FROM mart.ap_open_invoice WHERE currency_code <> 'IDR' GROUP BY currency_code ORDER BY 3 DESC"),
    ("AP", "Invoice yang jatuh tempo 7 hari ke depan",
     "SELECT vendor_name, invoice_num, due_date, currency_code, amount_remaining_entered, amount_remaining_idr "
     "FROM mart.ap_open_invoice WHERE due_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 7 ORDER BY due_date"),
    ("AP", "Pembayaran ke supplier bulan lalu",
     "SELECT vendor_name, COUNT(DISTINCT payment_number) AS jml_pembayaran, SUM(amount_idr) AS total_idr "
     "FROM mart.ap_payment_history "
     "WHERE payment_date >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month' "
     "AND payment_date < DATE_TRUNC('month', CURRENT_DATE) GROUP BY vendor_name ORDER BY 3 DESC"),
    ("AP", "Invoice yang sedang di-hold dan alasannya",
     "SELECT vendor_name, invoice_num, hold_code, hold_reason, hold_date, days_on_hold, invoice_amount_idr "
     "FROM mart.ap_invoice_hold ORDER BY days_on_hold DESC"),
    ("INV", "Lot yang expired dalam 90 hari",
     "SELECT item_code, item_desc, lot_number, expiration_date, onhand_qty, uom FROM mart.inv_onhand_lot "
     "WHERE days_to_expiry BETWEEN 0 AND 90 AND subinventory_type = 'GOOD' ORDER BY expiration_date"),
    ("INV", "Item dengan stok expired terbanyak",
     "SELECT item_code, item_desc, uom, SUM(onhand_qty) AS qty_expired, COUNT(*) AS jml_lot FROM mart.inv_onhand_lot "
     "WHERE days_to_expiry < 0 GROUP BY item_code, item_desc, uom ORDER BY 4 DESC LIMIT 20"),
    ("INV", "Stok per subinventory untuk satu item",
     "SELECT subinventory_code, subinventory_type, uom, SUM(onhand_qty) AS qty FROM mart.inv_onhand_lot "
     "WHERE UPPER(item_code) = UPPER('<kode item>') GROUP BY subinventory_code, subinventory_type, uom ORDER BY 1"),
    ("INV", "Stok di subinventory reject/karantina",
     "SELECT subinventory_type, item_code, item_desc, uom, SUM(onhand_qty) AS qty FROM mart.inv_onhand_lot "
     "WHERE subinventory_type IN ('REJECT','QUARANTINE') GROUP BY 1,2,3,4 ORDER BY 1, 5 DESC"),
    ("INV", "Pemakaian (keluar) item per bulan tahun ini",
     "SELECT period_start_date, period_name, item_code, uom, SUM(qty_out) AS qty_keluar FROM mart.inv_movement_daily "
     "WHERE txn_date >= DATE_TRUNC('year', CURRENT_DATE) AND UPPER(item_code) = UPPER('<kode item>') "
     "GROUP BY 1,2,3,4 ORDER BY 1"),
]
