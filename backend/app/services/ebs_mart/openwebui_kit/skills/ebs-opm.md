# OPM – Batch Produksi

## Kapan dipakai
batch, bets, produksi, status batch, jadwal produksi, batch terlambat, on time, schedule adherence, yield,
rendemen, hasil produksi, by-product, pemakaian bahan, konsumsi bahan, selisih bahan, lot bahan dipakai di
batch mana, penelusuran lot, traceability

## Mart
- mart.batch_status: 1 baris = batch (org 121). Kolom kunci: batch_no, batch_status_desc, formula, product_code,
  product_desc, product_plan_qty, product_actual_qty, yield_pct, plan_start_date, plan_cmplt_date,
  actual_cmplt_date, completion_delay_days, on_time, schedule_status.
- mart.batch_yield_variance: 1 baris = batch × produk/by-product. plan_qty, standard_qty, actual_qty, yield_pct.
- mart.batch_material_usage: 1 baris = batch × bahan × lot. line_standard_qty / line_actual_qty (per baris bahan,
  diulang per lot, satuan uom), line_variance_pct, lot_number, lot_qty_consumed (satuan lot_uom).

## Intent tool (utamakan)
- Status batch, batch terlambat, ketepatan jadwal → get_batch_status (group_by: none | status | schedule | product | month)
- Yield → get_batch_yield (group_by: product | batch | month; below_pct untuk yield rendah)
- Pemakaian bahan, selisih vs standar, lot bahan → get_batch_material_usage (lot_number untuk penelusuran lot → batch)

## Aturan bisnis
- Definisi sama dengan dashboard Production: periode batch = tanggal RENCANA MULAI (plan_start_date);
  yield = aktual ÷ rencana produk, hanya batch Completed/Closed; tepat waktu = aktual selesai ≤ rencana selesai.
- Status: Pending, WIP, Completed, Closed, Cancelled. Batch Cancelled tidak dihitung dalam yield.
- Standar bahan (line_standard_qty) = qty formula saat batch dibuat; selisih pemakaian hanya dihitung untuk batch
  Completed/Closed.
- Qty lot (lot_qty_consumed) dalam satuan primer item (lot_uom), bisa berbeda dari satuan baris (uom) — selalu
  sebut satuannya, jangan menjumlah qty berbeda satuan.
- Nilai Rupiah batch (biaya produksi) belum tersedia di mart — katakan terus terang bila ditanya.

## Jebakan umum
- Kolom line_* diulang di setiap baris lot: untuk total per bahan pakai group_by = ingredient, jangan menjumlah
  line_actual_qty dari baris per lot.
- Batch WIP/Pending yang melewati rencana selesai muncul sebagai "Belum selesai, lewat rencana"; batch lama yang
  tidak pernah ditutup bisa membuat angka ini tinggi — sebutkan tahun rencana mulainya.

## Contoh (golden queries)
Q: ketepatan jadwal batch tahun ini
SQL: SELECT COUNT(*) FILTER (WHERE on_time) tepat_waktu, COUNT(*) FILTER (WHERE actual_cmplt_date IS NOT NULL) selesai
     FROM mart.batch_status WHERE plan_start_date >= DATE_TRUNC('year', CURRENT_DATE);

Q: lot bahan L001 dipakai di batch mana
SQL: SELECT batch_no, product_code, item_desc, lot_qty_consumed, lot_uom FROM mart.batch_material_usage
     WHERE lot_number = 'L001';
