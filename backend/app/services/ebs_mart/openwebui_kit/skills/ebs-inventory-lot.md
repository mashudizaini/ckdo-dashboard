# INV – Stok per Lot & Mutasi

## Kapan dipakai
stok, persediaan, on hand, sisa stok, lot, batch bahan, ED, expired, kadaluarsa, mendekati expired,
gudang, subinventory, karantina, reject, mutasi, kartu stok, pemakaian, penerimaan barang

## Mart
- mart.inv_onhand_lot: 1 baris = item × subinventory × locator × lot di org 121 (stok saat ini).
  Kolom kunci: item_code, item_desc, uom, subinventory_code, subinventory_type (GOOD/REJECT/QUARANTINE),
  lot_number, lot_status, expiration_date, days_to_expiry, expiry_bucket, onhand_qty.
- mart.inv_movement_daily: 1 baris = item × tanggal × tipe transaksi × subinventory.
  Kolom kunci: txn_date, period_name, item_code, uom, transaction_type, qty_in, qty_out, net_qty.

## Intent tool (utamakan)
- Lot yang ED dalam N hari → get_expiring_lots (days, default subinventory_type GOOD)
- Stok item saat ini → get_stock_onhand (group_by: item | subinventory | lot)
- Nilai persediaan (Rupiah) → get_inventory_value (group_by: category | item | subinventory_type)
- Pemakaian/penerimaan per periode → get_stock_movement (group_by: type | item | day | month)

## Aturan bisnis
- Parameter `item` menerima kode item (cocok persis) ATAU nama bahan (cocok sebagian).
- Kategori item ada di kolom `item_category` (category set CKDO Inventory) dan bisa difilter lewat
  parameter `item_category` di get_expiring_lots / get_stock_onhand. Nilai: API, EXCIPIENT, PRIMER,
  SEKUNDER, LIQUID, LYOPHILLIZED, NA.
  "Bahan baku" = API + EXCIPIENT; "bahan kemas" = PRIMER + SEKUNDER. Sebutkan pemetaan ini di jawaban.
  LIQUID, LYOPHILLIZED dan NA: tampilkan apa adanya, jangan menebak artinya.
- "Stok yang bisa dipakai" = subinventory_type = 'GOOD'. Stok karantina dan reject dilaporkan terpisah.
- "Mendekati expired" tanpa angka → pakai 90 hari dan sebutkan asumsinya.
- Quantity selalu dengan uom. Jangan menjumlahkan qty item berbeda yang satuannya berbeda.
- days_to_expiry negatif = sudah expired.

## Jebakan umum
- Nilai persediaan (Rupiah) ada di mart.inv_valuation: qty on-hand SAAT INI × biaya OPM PMAC periode costing
  terakhir tiap item (cost_period_code). Ini valuasi saat ini, bukan saldo tutup buku periode — sebutkan
  periode costing yang dipakai. Item dengan has_cost = false belum punya biaya PMAC: nilainya kosong, bukan nol;
  sebutkan jumlah item tanpa biaya bila ada.
- inv_onhand_lot hanya org 121; inv_movement_daily memuat semua organisasi (kolom organization_code).
- Stok adalah snapshot per as_of, bukan stok historis. Stok per tanggal lampau tidak tersedia.

## Contoh (golden queries)
Q: lot yang expired dalam 90 hari
SQL: SELECT item_code, item_desc, lot_number, expiration_date, onhand_qty, uom
     FROM mart.inv_onhand_lot
     WHERE days_to_expiry BETWEEN 0 AND 90 AND subinventory_type = 'GOOD'
     ORDER BY expiration_date;
