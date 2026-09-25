# OM – Sales Order, Pengiriman & Penjualan

## Kapan dipakai
sales order, SO, order penjualan, backlog, belum dikirim, pengiriman, delivery, surat jalan, backorder,
penjualan, omzet, revenue, penjualan per customer / produk / bulan, top customer, ekspor, lokal, CMO

## Mart
- mart.so_backlog: 1 baris = baris SO yang masih open. Kolom kunci: order_number, customer_name, item_desc, uom,
  ordered_qty, shipped_qty, qty_to_ship, amount_to_ship_idr, due_date, days_late, delivery_status, business_type.
- mart.so_shipment_status: 1 baris = baris SO dengan status pengiriman (qty_shipped, qty_staged, qty_backordered,
  shipment_status, delivery_names, last_ship_confirm_date, lot_numbers).
- mart.sales_by_customer_item_month: 1 baris = customer × item × bulan GL × mata uang × tipe bisnis (penjualan
  yang SUDAH DIINVOICE). Kolom kunci: amount_idr, quantity, credit_memo_idr, period_name, business_type.

## Intent tool (utamakan)
- Order yang belum dikirim / terlambat → get_so_backlog (late_only, group_by: none | customer | item)
- Status kirim SO tertentu, backorder → get_so_shipment_status (order_number / status)
- Penjualan / omzet → get_sales_by_customer (period YYYY atau YYYY-MM; group_by: customer | item | month |
  customer_item | business_type)

## Aturan bisnis
- Hanya order tipe SO-LOCAL dan SO-EXPORT (sama dengan ETL penjualan dashboard). Tipe bisnis: SO-EXPORT = Export;
  baris SO-LOCAL dengan line type SO-TOLL IN-LOCAL = CMO; sisanya Local. Invoice tanpa SO = Non-SO.
- Backlog = baris open (open_flag Y, tidak cancel). qty_to_ship = order − kirim. Baris yang sudah terkirim tetapi
  belum ditutup/diinvoice tetap open dengan delivery_status "Sudah dikirim, belum ditutup".
- Nilai SO dalam IDR memakai kurs Corporate tanggal order; penjualan (invoice) memakai kurs invoice. Rupiah penuh.
- Penjualan dihitung per bulan GL invoice; credit memo/retur mengurangi bulan saat dikreditkan.
- Angka penjualan di sini = penjualan terinvoice dari Oracle AR. Laporan Sales Performance dashboard (budget vs
  aktual) memakai sumber lain (order) dan satuan juta — jangan dicampur; sebutkan sumbernya bila ditanya selisih.
- Setiap qty wajib dengan uom.

## Jebakan umum
- Sebagian besar backlog adalah order LAMA yang tidak pernah dikirim maupun ditutup (saat mart dibangun: 364 dari
  468 baris berasal dari order 2020–2024). Untuk pertanyaan backlog, sebutkan pemisahan ini: pakai
  group_by = year untuk melihat umur backlog, atau ordered_from untuk backlog aktif, dan sarankan order lama
  ditutup/dibatalkan di EBS. Jadwal kirim banyak yang sama dengan tanggal order, jadi status "Terlambat" pada
  order lama tidak berarti keterlambatan operasional saat ini.
- "Penjualan bulan ini" berarti invoice dengan GL date bulan ini, bukan order yang dibuat bulan ini — kalau user
  sepertinya maksud order, tanyakan dulu.
- Satu SO bisa punya banyak baris dan shipment; jumlahkan per order_number bila ditanya per order.

## Contoh (golden queries)
Q: penjualan per customer tahun ini
SQL: SELECT customer_name, SUM(amount_idr) penjualan_idr FROM mart.sales_by_customer_item_month
     WHERE fiscal_year = EXTRACT(YEAR FROM CURRENT_DATE) GROUP BY customer_name ORDER BY 2 DESC;
