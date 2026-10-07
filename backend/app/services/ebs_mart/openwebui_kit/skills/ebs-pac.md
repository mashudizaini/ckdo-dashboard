# PAC – Business Plan (rencana/target) dan Plan vs Actual

## Kapan dipakai
business plan, BP, rencana, target, plan, proyeksi, budget tahunan PAC, target penjualan, sales plan,
manufacture plan, purchase plan, investment plan / capex, personnel plan / headcount plan, cashflow plan,
plan vs actual, realisasi vs target, pencapaian target, achievement

## Mart
- mart.pac_business_plan: 1 baris = 1 sel angka di workbook "<tahun> Business plan.xlsx" milik PAC (BUKAN dari
  Oracle). Kolom kunci: plan_year, section, sheet_title, line_path (induk > anak), column_header, period_type
  (year / month / quarter / half / other), period_year, period_month, scenario (plan | pembanding), measure
  (value | ratio | growth), unit, amount_idr, quantity, pct, keterangan.
- Bagian (section): 1-1 P&L tahunan; 1-2 P&L bulanan ringkasan (1-2.a Local, 1-2.b CMO & Others, 1-2.c Export);
  2-1 sales plan per produk (nilai); 2-2 sales plan per produk (qty); 3-1 COGS per bisnis; 3-2 COGS per produk;
  4 manufacture plan; 5 investment plan; 6-1 purchase plan nilai; 6-2 purchase plan qty; 7 registration schedule;
  8 sales & marketing expenses; 9 personnel plan; 10 cashflow.

## Intent tool (utamakan)
- Target penjualan vs realisasi EBS (per bisnis / per bulan, sebulan, YTD, setahun) →
  pac_get_sales_plan_vs_actual (year, month, ytd, basis gross|net|customer, group_by business|month|business_month)
- Angka plan lainnya → pac_get_business_plan (year, section, line, period, scenario, measure).
  period: tahunan (total plan + tahun pembanding) | YYYY | YYYY-MM | YYYY-Qn. section '1-2' = sheet ringkasan saja;
  '1' = 1-1, 1-2, 1-2.a/b/c sekaligus (nama baris berulang antar sheet — bedakan dengan sheet_title).
  Tanpa section dan line, tool hanya mengembalikan daftar bagian — pakai itu dulu bila ragu bagian mana.
- Plan vs actual untuk hal lain: ambil plan dengan pac_get_business_plan, ambil aktual dengan tool EBS yang sesuai
  (P&L → gl_get_pl; produksi → opm_get_batch / opm_get_yield; penjualan per produk/qty → sales_get_summary), lalu
  tampilkan berdampingan. Sebutkan bahwa definisi bisa berbeda (plan disusun per bisnis/produk PAC, aktual dari EBS).

## Aturan bisnis
- amount_idr sudah dalam Rupiah penuh (sheet ditulis "mil Rp" = juta Rupiah, sudah dikali 1.000.000).
  amount_in_unit = angka seperti tertulis di sheet.
- Kolom "2026(P)" = total rencana tahun plan; kolom tahun sebelumnya (scenario pembanding) adalah angka pembanding
  yang dicantumkan dokumen (estimasi/aktual saat plan disusun) — BUKAN data EBS. Untuk aktual pakai tool EBS.
- Baris P&L: Customer Sales (penjualan distributor ke pasar) → CKD OTTO Gross Sales → dikurangi distribution fee,
  diskon, retur, freight → CKD OTTO Net Sales. Invoice EBS paling sebanding dengan Gross Sales (basis default
  pac_get_sales_plan_vs_actual). Sebutkan basis yang dipakai.
- Bisnis: Local (Public + Private), CMO & Others, Export — sama dengan business_type EBS (Local / CMO / Export).
  Non-SO di EBS tidak punya padanan di plan.
- Bulan berjalan belum lengkap: sebutkan bila periode mencakup bulan ini.
- Jika plan_year yang diminta tidak ada (tool kosong), katakan Business Plan tahun itu belum diimpor.
- Data ini rahasia PAC: hanya peran yang diberi akses pac_business_plan. Jika 403, sampaikan apa adanya.
