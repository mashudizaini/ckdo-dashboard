"""
EIS Tool Calling — Oracle EBS Data Chat
─────────────────────────────────────────
The chat model never sees or writes raw SQL. Every tool below maps to one
predefined, parameterized SELECT against Postgres EIS (172.21.2.209:5433,
schema `eis`, ETL'd from Oracle EBS) run as a dedicated `chat_readonly`
role that only has SELECT on schema `eis` — even a prompt-injected or
hallucinated argument can't turn into a write, because the DB user itself
can't write. See sumber/AI_Chat_Implementation_Guide.md section 5.

use_connection() below lets a caller (EBS Chat, see ebs_chat_service.py)
route every tool call in this module through one caller-supplied connection
instead of the default per-call chat_readonly connection — needed so a
whole tool-calling turn runs on a single connection/transaction, which is
required for Postgres RLS session variables (SET LOCAL app.*) to actually
apply to the queries these tools issue. The Dashboard's own internal
Oracle EBS chat (oracle_chat_service.py) never calls use_connection(), so
its behavior is unchanged — every _query() there still opens/closes its
own chat_readonly connection exactly as before.
"""
import contextvars
import re
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from app.config import get_settings

settings = get_settings()

_scoped_conn: contextvars.ContextVar = contextvars.ContextVar("eis_tools_scoped_conn", default=None)


@contextmanager
def use_connection(conn):
    token = _scoped_conn.set(conn)
    try:
        yield
    finally:
        _scoped_conn.reset(token)

# Perbandingan teks di bawah tidak peka huruf besar/kecil, dan untuk kolom
# kategori dicocokkan sebagai awalan (LIKE 'nilai%') alih-alih persis.
#
# Nilai-nilai ini datang dari model, bukan dari daftar pilihan: ia menuliskan
# "direct material" sementara Oracle menyimpan "DIRECT MATERIAL". Perbandingan
# persis mengembalikan nol baris, dan nol baris dilaporkan sebagai "tidak ada
# data untuk periode itu" — jawaban yang terdengar pasti padahal salah, dan
# jauh lebih berbahaya daripada sebuah error. Persis itu yang terjadi pada
# 2026-09-24: pembelian direct material Januari 2026 dinyatakan tidak ada,
# padahal tabelnya berisi 19 PO senilai Rp 1,39 miliar.
#
# Tidak peka huruf saja ternyata belum cukup: model mengirim "Direct", bukan
# "DIRECT MATERIAL". Karena itu kolom kategori dicocokkan sebagai awalan.
#
# Awalan, bukan "mengandung", dan ini bukan detail sepele: "INDIRECT MATERIAL"
# memuat kata "direct", sehingga pencarian mengandung akan menjawab pertanyaan
# tentang direct material dengan angka indirect — salah tanpa terlihat salah.
# Dijangkar di awal, "direct" hanya cocok ke DIRECT MATERIAL dan "indirect"
# hanya ke INDIRECT MATERIAL.
#
# Kode barang dan kode produk sengaja tetap dicocokkan persis (hanya diabaikan
# huruf besar/kecilnya): awalan pada kode akan mencocokkan barang yang berbeda.
#
# UPPER() memang membuat indeks pada kolom itu tidak terpakai. Tabel-tabel ini
# kecil (fact_purchasing hanya berisi agregat per periode), dan menjawab benar
# lebih penting daripada menghemat pemindaian tabel sekecil itu.

EIS_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_sales_performance",
            "description": "Ambil data performa penjualan (budget plan vs aktual vs tahun lalu) per periode, opsional difilter per produk atau tipe bisnis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "description": "Periode fiskal: YYYY-MM untuk satu bulan (contoh 2026-06), atau YYYY untuk satu tahun penuh (contoh 2025). Pakai bentuk tahun untuk pertanyaan sepanjang tahun \u2014 jangan memanggil tool ini dua belas kali."},
                    "product_code": {"type": "string", "description": "Opsional. Kode produk, contoh DOC01, PAC02"},
                    "business_type": {"type": "string", "description": "Opsional. Salah satu dari: Local, Export, CMO"},
                },
                "required": ["period"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_production_performance",
            "description": "Ambil data performa produksi (budget plan vs aktual qty, yield, batch size) per periode.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "description": "Periode fiskal: YYYY-MM untuk satu bulan (contoh 2026-06), atau YYYY untuk satu tahun penuh (contoh 2025). Pakai bentuk tahun untuk pertanyaan sepanjang tahun \u2014 jangan memanggil tool ini dua belas kali."},
                },
                "required": ["period"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_budget_vs_actual",
            "description": "Bandingkan budget vs realisasi anggaran per grup departemen dan periode.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "description": "Periode fiskal: YYYY-MM untuk satu bulan (contoh 2026-06), atau YYYY untuk satu tahun penuh (contoh 2025). Pakai bentuk tahun untuk pertanyaan sepanjang tahun \u2014 jangan memanggil tool ini dua belas kali."},
                    "dept_group": {"type": "string", "description": "Opsional. Salah satu dari: Plant Direct, SM, Admin"},
                },
                "required": ["period"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_financial_summary",
            "description": "Ambil ringkasan keuangan (net profit, cash flow) budget plan vs aktual untuk satu periode.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "description": "Periode fiskal: YYYY-MM untuk satu bulan (contoh 2026-06), atau YYYY untuk satu tahun penuh (contoh 2025). Pakai bentuk tahun untuk pertanyaan sepanjang tahun \u2014 jangan memanggil tool ini dua belas kali."},
                },
                "required": ["period"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cogs_performance",
            "description": "Ambil data sales, COGS, dan EBIT per produk untuk satu periode — untuk pertanyaan margin/profitabilitas per produk.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "description": "Periode fiskal: YYYY-MM untuk satu bulan (contoh 2026-06), atau YYYY untuk satu tahun penuh (contoh 2025). Pakai bentuk tahun untuk pertanyaan sepanjang tahun \u2014 jangan memanggil tool ini dua belas kali."},
                    "product_code": {"type": "string", "description": "Opsional. Kode produk, contoh DOC01, PAC02"},
                    "business_type": {"type": "string", "description": "Opsional. Salah satu dari: Local, Export, CMO"},
                },
                "required": ["period"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_ar_ap_summary",
            "description": "Ambil ringkasan piutang (AR/DSO) dan hutang (AP/DPO) usaha, termasuk net working capital days, untuk satu periode.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "description": "Periode fiskal: YYYY-MM untuk satu bulan (contoh 2026-06), atau YYYY untuk satu tahun penuh (contoh 2025). Pakai bentuk tahun untuk pertanyaan sepanjang tahun \u2014 jangan memanggil tool ini dua belas kali."},
                },
                "required": ["period"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_inventory_summary",
            "description": "Ambil ringkasan nilai persediaan (inventory) dan days inventory outstanding (DIO) untuk satu periode.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "description": "Periode fiskal: YYYY-MM untuk satu bulan (contoh 2026-06), atau YYYY untuk satu tahun penuh (contoh 2025). Pakai bentuk tahun untuk pertanyaan sepanjang tahun \u2014 jangan memanggil tool ini dua belas kali."},
                },
                "required": ["period"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_purchasing_performance",
            "description": "Ambil data trend Purchase Order (jumlah PO dan nilai PO dalam IDR) per tipe material (Direct/Indirect) untuk satu periode.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "description": "Periode fiskal: YYYY-MM untuk satu bulan (contoh 2026-06), atau YYYY untuk satu tahun penuh (contoh 2025). Pakai bentuk tahun untuk pertanyaan sepanjang tahun \u2014 jangan memanggil tool ini dua belas kali."},
                    "material_type": {"type": "string", "description": "Tipe material, dicocokkan sebagai awalan dan tidak peka huruf besar/kecil. Nilai yang ada: DIRECT MATERIAL, INDIRECT MATERIAL, Unclassified."},
                },
                "required": ["period"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_purchase_order_detail",
            "description": "Cari data PO (Purchase Order) individual — nomor PO, item, supplier, quantity, harga per unit — berdasarkan supplier, nama barang, kode item, dan/atau nomor PO. Untuk pertanyaan 'PO apa saja dari supplier X', 'PO nomor berapa untuk item Y', bukan sekadar total/trend (untuk itu pakai get_purchasing_performance).",
            "parameters": {
                "type": "object",
                "properties": {
                    "supplier_name": {"type": "string", "description": "Opsional. Nama supplier (partial match), contoh IFORTE"},
                    "item_code": {"type": "string", "description": "Opsional. Kode item Oracle persis, contoh CKD21R0303. Jangan diisi nama bahan \u2014 untuk itu pakai item_name."},
                    "item_name": {"type": "string", "description": "Opsional. Nama atau deskripsi barang (partial match), contoh Bortezomib, Paracetamol, LABEL. Pakai ini kalau yang disebut pengguna adalah nama bahan/barang, bukan kode."},
                    "po_number": {"type": "string", "description": "Opsional. Nomor PO (partial match)"},
                    "period": {"type": "string", "description": "Opsional. Periode fiskal: YYYY-MM untuk satu bulan (contoh 2026-06), atau YYYY untuk satu tahun penuh (contoh 2025). Pakai bentuk tahun untuk pertanyaan sepanjang tahun \u2014 jangan memanggil tool ini dua belas kali."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sales_order_detail",
            "description": "Cari data Sales Order individual — nomor order, item, customer, nilai — berdasarkan nama customer, kode item, nomor order, dan/atau tahun. Untuk pertanyaan 'total penjualan customer X', 'order apa saja dari customer Y', 'penjualan item Z ke customer mana saja' — bukan sekadar total/trend perusahaan (untuk itu pakai get_sales_performance). Kalau user tanya 'total' untuk satu customer/tahun, jumlahkan sendiri amount_idr dari baris-baris yang dikembalikan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Opsional. Nama customer (partial match), contoh SAIDAL"},
                    "item_code": {"type": "string", "description": "Opsional. Kode item Oracle"},
                    "order_number": {"type": "string", "description": "Opsional. Nomor Sales Order (partial match)"},
                    "business_type": {"type": "string", "description": "Opsional. Salah satu dari: Local, Export, CMO"},
                    "year": {"type": "integer", "description": "Opsional. Tahun fiskal 4 digit, contoh 2025 — untuk pertanyaan 'total setahun'"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_employee_directory",
            "description": "Cari daftar / total karyawan (nama, posisi, department, team, tanggal masuk, status, tanggal & alasan resign) — untuk pertanyaan 'siapa saja di tim X', cari data karyawan tertentu, 'berapa total karyawan resign/aktif saat ini' (hitung dari jumlah baris hasil, employment_status='Resign' untuk yang sudah keluar, 'Active' untuk yang masih bekerja), atau 'kapan/kenapa si X resign' (pakai field resign_date dan resign_reason di hasilnya — SISTEM INI MENYIMPAN tanggal & alasan resign, jangan bilang tidak ada).",
            "parameters": {
                "type": "object",
                "properties": {
                    "department": {"type": "string", "description": "Opsional. Salah satu dari: Administration, Sales & Marketing, Strategy & Development, Plant"},
                    "team": {"type": "string", "description": "Opsional. Nama tim, contoh IT, HRGA, Purchasing, Accounting"},
                    "full_name": {"type": "string", "description": "Opsional. Cari berdasarkan nama (partial match)"},
                    "employment_status": {"type": "string", "description": "Opsional. 'Active' (masih bekerja) atau 'Resign' (sudah keluar) — pakai ini untuk pertanyaan total/daftar karyawan resign atau aktif"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_employee_headcount",
            "description": "Ambil data headcount karyawan (aktual vs plan, kumulatif resign) per grup departemen untuk satu periode.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "description": "Periode fiskal: YYYY-MM untuk satu bulan (contoh 2026-06), atau YYYY untuk satu tahun penuh (contoh 2025). Pakai bentuk tahun untuk pertanyaan sepanjang tahun \u2014 jangan memanggil tool ini dua belas kali."},
                    "dept_group": {"type": "string", "description": "Opsional. Grup departemen, contoh Plant Direct, SM, Admin"},
                },
                "required": ["period"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_daily_sales",
            "description": "Ambil data Daily Sales (penjualan harian per hari kerja) beserta akumulasi dan target bulanannya. Sumbernya unggahan Excel EIS Data Upload, bukan Oracle. Sebutkan tahun; bulan opsional dalam bahasa Inggris (january, february, ...).",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {"type": "integer", "description": "Tahun fiskal, misalnya 2025."},
                    "month": {"type": "string", "description": "Nama bulan dalam bahasa Inggris, misalnya january. Kosongkan untuk seluruh tahun."},
                },
                "required": ["year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tablespace_usage",
            "description": "Ambil kondisi tablespace Oracle EBS terkini (persen terpakai terhadap ukuran maksimum/autoextend). Gunakan min_used_pct untuk menyaring, misalnya 90 untuk 'tablespace yang lebih dari 90%'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "min_used_pct": {"type": "number", "description": "Hanya tampilkan tablespace dengan pemakaian >= nilai ini (persen)."},
                    "tablespace_name": {"type": "string", "description": "Saring per nama tablespace (pencocokan sebagian, tidak peka huruf besar/kecil)."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tablespace_trend",
            "description": "Tren pemakaian sebuah tablespace per hari (nilai tertinggi harian) untuk melihat laju pertumbuhan dan memperkirakan kapan penuh.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tablespace_name": {"type": "string", "description": "Nama tablespace (pencocokan sebagian)."},
                    "days": {"type": "integer", "description": "Rentang hari ke belakang, default 30."},
                },
                "required": ["tablespace_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_server_resources",
            "description": "Kondisi CPU, memori, swap, load, dan uptime server terkini. Tanpa argumen mengembalikan semua server (DB dan Aplikasi).",
            "parameters": {
                "type": "object",
                "properties": {
                    "server": {"type": "string", "description": "Saring per server: 'db', 'app', atau sebagian nama labelnya."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_disk_usage",
            "description": "Pemakaian filesystem per mount point di server DB dan Aplikasi. Gunakan min_used_pct untuk mencari partisi yang hampir penuh.",
            "parameters": {
                "type": "object",
                "properties": {
                    "server": {"type": "string", "description": "Saring per server: 'db', 'app', atau sebagian nama labelnya."},
                    "min_used_pct": {"type": "number", "description": "Hanya tampilkan mount point dengan pemakaian >= nilai ini (persen)."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_oracle_activity",
            "description": "Jumlah sesi Oracle aktif/idle/terblokir dan antrean concurrent request (pending/running) terkini, beserta wait event teratas.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

_PERIOD_RE = re.compile(r"^(\d{4})(?:-(\d{1,2}))?$")


def _parse_period(period: str) -> tuple[int, "int | None"]:
    """Accepts YYYY-MM for one month, or YYYY for a whole year.

    The year form exists because without it "total pembelian sepanjang 2025"
    forced the model to call the same tool twelve times, once per month. That
    is slow, and the accumulated tool output crowded out the final answer:
    on 2026-09-24 such a question came back as ten separate calls and then no
    answer at all, because the reply hit max_tokens before any text was
    written. One call per year fixes the cause rather than the symptom.

    Returns (fiscal_year, None) for the year form; every query treats a None
    month as "all periods in that year"."""
    m = _PERIOD_RE.match((period or "").strip())
    if not m:
        raise ValueError(f"Invalid period format '{period}' — expected YYYY-MM or YYYY")
    fiscal_year = int(m.group(1))
    if m.group(2) is None:
        return fiscal_year, None
    period_num = int(m.group(2))
    if not (1 <= period_num <= 12):
        raise ValueError(f"Invalid month in period '{period}'")
    return fiscal_year, period_num


def _get_conn():
    override = _scoped_conn.get()
    if override is not None:
        return override
    return psycopg2.connect(settings.eis_database_url)


def _query(sql: str, params: dict) -> list[dict]:
    # Defense-in-depth independent of the DB role's own grants — every tool
    # in this module is a predefined SELECT, so anything else here would
    # mean a bug in this file, not a bad argument from the model.
    assert sql.strip().upper().startswith("SELECT"), "eis_tools only issues SELECT statements"
    conn = _get_conn()
    owns_conn = _scoped_conn.get() is None
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
    finally:
        if owns_conn:
            conn.close()


def get_sales_performance(period: str, product_code: str = None, business_type: str = None) -> list[dict]:
    fy, pnum = _parse_period(period)
    # LEFT JOIN dim_product — some fact_sales rows have no product_id resolved
    # by the ETL (e.g. aggregated entries); an INNER JOIN would silently drop
    # real revenue rows instead of just showing a null product.
    return _query(
        """
        SELECT dp.product_code, dp.product_name, fs.business_type, fs.market,
               fs.bp_amount, fs.actual_amount, fs.prior_year_actual,
               (fs.actual_amount - fs.bp_amount) AS variance_vs_budget,
               CASE WHEN fs.prior_year_actual > 0
                    THEN round(((fs.actual_amount - fs.prior_year_actual) / fs.prior_year_actual * 100)::numeric, 1)
               END AS yoy_growth_pct
        FROM eis.fact_sales fs
        JOIN eis.dim_period per ON per.id = fs.period_id
        LEFT JOIN eis.dim_product dp ON dp.id = fs.product_id
        WHERE per.fiscal_year = %(fy)s AND (%(pnum)s IS NULL OR per.period_num = %(pnum)s)
          AND (%(product_code)s IS NULL OR UPPER(dp.product_code) = UPPER(%(product_code)s))
          AND (%(business_type)s IS NULL OR UPPER(fs.business_type) LIKE UPPER(%(business_type)s) || '%%')
        ORDER BY fs.actual_amount DESC
        """,
        {"fy": fy, "pnum": pnum, "product_code": product_code, "business_type": business_type},
    )


def get_production_performance(period: str) -> list[dict]:
    fy, pnum = _parse_period(period)
    return _query(
        """
        SELECT per.period_name, per.fiscal_year, fp.segment, fp.bp_qty, fp.actual_qty,
               fp.batch_size, fp.yield_qty,
               CASE WHEN fp.bp_qty > 0
                    THEN round((fp.actual_qty / fp.bp_qty * 100)::numeric, 1)
               END AS achievement_pct
        FROM eis.fact_production fp
        JOIN eis.dim_period per ON per.id = fp.period_id
        WHERE per.fiscal_year = %(fy)s AND (%(pnum)s IS NULL OR per.period_num = %(pnum)s)
        """,
        {"fy": fy, "pnum": pnum},
    )


def get_budget_vs_actual(period: str, dept_group: str = None) -> list[dict]:
    fy, pnum = _parse_period(period)
    return _query(
        """
        SELECT per.period_name, per.fiscal_year, fb.dept_group, fb.bp_amount, fb.actual_amount,
               (fb.actual_amount - fb.bp_amount) AS variance
        FROM eis.fact_budget fb
        JOIN eis.dim_period per ON per.id = fb.period_id
        WHERE per.fiscal_year = %(fy)s AND (%(pnum)s IS NULL OR per.period_num = %(pnum)s)
          AND (%(dept_group)s IS NULL OR UPPER(fb.dept_group) LIKE UPPER(%(dept_group)s) || '%%')
        ORDER BY fb.dept_group
        """,
        {"fy": fy, "pnum": pnum, "dept_group": dept_group},
    )


def get_financial_summary(period: str) -> list[dict]:
    fy, pnum = _parse_period(period)
    return _query(
        """
        SELECT per.period_name, per.fiscal_year,
               ff.net_profit_bp, ff.net_profit_actual, ff.net_profit_actual_cumulative,
               ff.cf_beginning_balance_actual, ff.cf_cash_in_actual, ff.cf_cash_out_actual,
               ff.cf_ending_balance_actual
        FROM eis.fact_financial ff
        JOIN eis.dim_period per ON per.id = ff.period_id
        WHERE per.fiscal_year = %(fy)s AND (%(pnum)s IS NULL OR per.period_num = %(pnum)s)
        """,
        {"fy": fy, "pnum": pnum},
    )


def get_cogs_performance(period: str, product_code: str = None, business_type: str = None) -> list[dict]:
    fy, pnum = _parse_period(period)
    return _query(
        """
        SELECT dp.product_code, dp.product_name, fc.business_type,
               fc.sales_amount, fc.cogs_total, fc.ebit_amount,
               CASE WHEN fc.sales_amount > 0
                    THEN round((fc.ebit_amount / fc.sales_amount * 100)::numeric, 1)
               END AS ebit_pct
        FROM eis.fact_cogs fc
        JOIN eis.dim_period per ON per.id = fc.period_id
        JOIN eis.dim_product dp ON dp.id = fc.product_id
        WHERE per.fiscal_year = %(fy)s AND (%(pnum)s IS NULL OR per.period_num = %(pnum)s)
          AND (%(product_code)s IS NULL OR UPPER(dp.product_code) = UPPER(%(product_code)s))
          AND (%(business_type)s IS NULL OR UPPER(fc.business_type) LIKE UPPER(%(business_type)s) || '%%')
        ORDER BY fc.sales_amount DESC
        """,
        {"fy": fy, "pnum": pnum, "product_code": product_code, "business_type": business_type},
    )


def get_ar_ap_summary(period: str) -> list[dict]:
    fy, pnum = _parse_period(period)
    return _query(
        """
        SELECT per.period_name, per.fiscal_year,
               r.dso_ar_avg, r.dso_days, r.dpo_ap_avg, r.dpo_days,
               round((r.dso_days + COALESCE(r.dio_days,0) - r.dpo_days)::numeric, 1) AS nwc_days
        FROM eis.fact_financial_ratio r
        JOIN eis.dim_period per ON per.id = r.period_id
        WHERE per.fiscal_year = %(fy)s AND (%(pnum)s IS NULL OR per.period_num = %(pnum)s)
        """,
        {"fy": fy, "pnum": pnum},
    )


def get_inventory_summary(period: str) -> list[dict]:
    fy, pnum = _parse_period(period)
    return _query(
        """
        SELECT per.period_name, per.fiscal_year,
               r.dio_inv_avg, r.dio_cogs, r.dio_days
        FROM eis.fact_financial_ratio r
        JOIN eis.dim_period per ON per.id = r.period_id
        WHERE per.fiscal_year = %(fy)s AND (%(pnum)s IS NULL OR per.period_num = %(pnum)s)
          AND r.dio_days IS NOT NULL
        """,
        {"fy": fy, "pnum": pnum},
    )


def get_purchasing_performance(period: str, material_type: str = None) -> list[dict]:
    fy, pnum = _parse_period(period)
    return _query(
        """
        SELECT per.period_name, per.fiscal_year, p.material_type,
               p.po_count, p.po_value
        FROM eis.fact_purchasing p
        JOIN eis.dim_period per ON per.id = p.period_id
        WHERE per.fiscal_year = %(fy)s AND (%(pnum)s IS NULL OR per.period_num = %(pnum)s)
          AND (%(material_type)s IS NULL OR UPPER(p.material_type) LIKE UPPER(%(material_type)s) || '%%')
        ORDER BY p.material_type
        """,
        {"fy": fy, "pnum": pnum, "material_type": material_type},
    )


def get_purchase_order_detail(
    supplier_name: str = None, item_code: str = None, item_name: str = None,
    po_number: str = None, period: str = None,
) -> list[dict]:
    """Line-item PO search — backed by eis.fact_po_line (etl_po_lines),
    the same table Purchasing History/Price Analysis read from. Added so
    the chatbot can answer "which POs from supplier X" questions that
    get_purchasing_performance's aggregate-only shape never could.

    item_name searches item_description; item_code stays an exact match on
    the Oracle code. Both exist because people ask by substance name, not by
    code: "pembelian API Bortezomib" sent Bortezomib into item_code, which
    matched nothing and was reported as no purchases at all — while
    item_description held five matching lines with supplier, quantity and
    unit price. A name is not a code, and only one of them can be matched
    exactly."""
    fy = pnum = None
    if period:
        fy, pnum = _parse_period(period)
    return _query(
        """
        SELECT po_number, line_num, item_code, item_description, supplier_name,
               material_type, currency_code, quantity, unit_price, amount_orig, amount_idr,
               creation_date, closure_status
        FROM eis.fact_po_line
        WHERE (%(supplier_name)s IS NULL OR supplier_name ILIKE %(supplier_like)s)
          AND (%(item_code)s    IS NULL OR UPPER(item_code) = UPPER(%(item_code)s))
          AND (%(item_name)s    IS NULL OR item_description ILIKE %(item_name_like)s)
          AND (%(po_number)s    IS NULL OR po_number ILIKE %(po_like)s)
          AND (%(fy)s   IS NULL OR EXTRACT(YEAR FROM creation_date) = %(fy)s)
          AND (%(pnum)s IS NULL OR EXTRACT(MONTH FROM creation_date) = %(pnum)s)
        ORDER BY creation_date DESC
        LIMIT 50
        """,
        {
            "supplier_name": supplier_name, "supplier_like": f"%{supplier_name}%" if supplier_name else None,
            "item_code": item_code,
            "item_name": item_name, "item_name_like": f"%{item_name}%" if item_name else None,
            "po_number": po_number, "po_like": f"%{po_number}%" if po_number else None,
            "fy": fy, "pnum": pnum,
        },
    )


def get_sales_order_detail(
    customer_name: str = None, item_code: str = None, order_number: str = None,
    business_type: str = None, year: int = None,
) -> list[dict]:
    """Line-item Sales Order search — backed by eis.fact_sales_order
    (etl_sales_orders), the same table the Open Sales Order dashboard
    reads from. Added so the chatbot can answer "total sales for customer
    X" questions that get_sales_performance's aggregate-only shape never
    could (verified live: "total penjualan customer GROUPE INDUSTRIEL
    SAIDAL SPA" came back not-found before this tool existed)."""
    return _query(
        """
        SELECT order_number, line_num, item_code, item_description, customer_name,
               business_type, currency_code, quantity, unit_selling_price,
               amount_orig, amount_idr, flow_status_code, ordered_date
        FROM eis.fact_sales_order
        WHERE (%(customer_name)s  IS NULL OR customer_name ILIKE %(customer_like)s)
          AND (%(item_code)s      IS NULL OR UPPER(item_code) = UPPER(%(item_code)s))
          AND (%(order_number)s   IS NULL OR order_number ILIKE %(order_like)s)
          AND (%(business_type)s  IS NULL OR UPPER(business_type) LIKE UPPER(%(business_type)s) || '%%')
          AND (%(year)s IS NULL OR EXTRACT(YEAR FROM ordered_date) = %(year)s)
        ORDER BY ordered_date DESC
        LIMIT 100
        """,
        {
            "customer_name": customer_name, "customer_like": f"%{customer_name}%" if customer_name else None,
            "item_code": item_code,
            "order_number": order_number, "order_like": f"%{order_number}%" if order_number else None,
            "business_type": business_type,
            "year": year,
        },
    )


def get_employee_directory(department: str = None, team: str = None, full_name: str = None, employment_status: str = None) -> list[dict]:
    return _query(
        """
        SELECT employee_number, full_name, department, division, team, position_title,
               hire_date, employment_status, resign_date, resign_reason
        FROM eis.dim_employee
        WHERE (%(department)s IS NULL OR UPPER(department) LIKE UPPER(%(department)s) || '%%')
          AND (%(team_like)s IS NULL OR team ILIKE %(team_like)s)
          AND (%(name_like)s IS NULL OR full_name ILIKE %(name_like)s)
          AND (%(employment_status)s IS NULL OR UPPER(employment_status) LIKE UPPER(%(employment_status)s) || '%%')
        ORDER BY department, team, full_name
        LIMIT 500
        """,
        {
            "department": department,
            "team_like": f"%{team}%" if team else None,
            "name_like": f"%{full_name}%" if full_name else None,
            "employment_status": employment_status,
        },
    )


def get_employee_headcount(period: str, dept_group: str = None) -> list[dict]:
    fy, pnum = _parse_period(period)
    return _query(
        """
        SELECT per.period_name, per.fiscal_year, e.dept_group,
               e.headcount, e.plan_headcount, e.resigned_cumulative
        FROM eis.fact_employee e
        JOIN eis.dim_period per ON per.id = e.period_id
        WHERE per.fiscal_year = %(fy)s AND (%(pnum)s IS NULL OR per.period_num = %(pnum)s)
          AND (%(dept_group)s IS NULL OR UPPER(e.dept_group) LIKE UPPER(%(dept_group)s) || '%%')
        """,
        {"fy": fy, "pnum": pnum, "dept_group": dept_group},
    )


# ── IT / DBA infrastructure tools ────────────────────────────────────────────
# These read the eis.fact_it_* snapshots written every 15 minutes by
# app.tasks.eis_etl_tasks.etl_it_monitoring. They are restricted to the "IT"
# module in ebs_chat_service.MODULE_TOOL_MAP: mount points, server addresses
# and remaining capacity are reconnaissance material, not company-wide facts
# like sales figures, so they stay hidden from callers without that module.
#
# Each one reads the newest snapshot rather than an average, because "which
# tablespace is above 90%" is a question about now. The trend tool is the
# exception and is the reason the tables are append-only.


def get_tablespace_usage(min_used_pct: float = None, tablespace_name: str = None) -> list[dict]:
    """Latest tablespace snapshot, optionally only those above a threshold."""
    sql = """
        SELECT tablespace_name, used_pct, used_gb, max_gb, status, contents, captured_at
          FROM eis.fact_it_tablespace
         WHERE captured_at = (SELECT MAX(captured_at) FROM eis.fact_it_tablespace)
    """
    params = {}
    if min_used_pct is not None:
        sql += " AND used_pct >= %(min_used_pct)s"
        params["min_used_pct"] = min_used_pct
    if tablespace_name:
        sql += " AND UPPER(tablespace_name) LIKE UPPER(%(tablespace_name)s)"
        params["tablespace_name"] = f"%{tablespace_name}%"
    sql += " ORDER BY used_pct DESC"
    return _query(sql, params)


def get_tablespace_trend(tablespace_name: str, days: int = 30) -> list[dict]:
    """Daily high-water mark per tablespace over the last N days.

    MAX per day rather than the raw 15-minute rows: the question behind this
    is capacity planning, and a day's peak is what a threshold would have
    tripped on. Returning every snapshot would also bury the model in ~96
    rows per tablespace per day.
    """
    sql = """
        SELECT DATE(captured_at)     AS day,
               tablespace_name,
               MAX(used_pct)         AS used_pct,
               MAX(used_gb)          AS used_gb,
               MAX(max_gb)           AS max_gb
          FROM eis.fact_it_tablespace
         WHERE captured_at >= NOW() - (%(days)s || ' days')::interval
           AND UPPER(tablespace_name) LIKE UPPER(%(tablespace_name)s)
         GROUP BY DATE(captured_at), tablespace_name
         ORDER BY day, tablespace_name
    """
    return _query(sql, {"days": days, "tablespace_name": f"%{tablespace_name}%"})


def get_server_resources(server: str = None) -> list[dict]:
    """Latest CPU / memory / swap / load / uptime per server."""
    sql = """
        SELECT server_key, server_label, server_ip, status,
               cpu_pct, cpu_count, memory_pct, memory_used_gb, memory_total_gb,
               swap_pct, load_1, uptime, error_message, captured_at
          FROM eis.fact_it_server_metrics
         WHERE captured_at = (SELECT MAX(captured_at) FROM eis.fact_it_server_metrics)
    """
    params = {}
    if server:
        sql += " AND (UPPER(server_key) = UPPER(%(server)s) OR UPPER(server_label) LIKE UPPER(%(server_like)s))"
        params["server"] = server
        params["server_like"] = f"%{server}%"
    sql += " ORDER BY server_key"
    return _query(sql, params)


def get_disk_usage(server: str = None, min_used_pct: float = None) -> list[dict]:
    """Latest filesystem usage per mount point, optionally filtered."""
    sql = """
        SELECT server_key, server_label, mount_point, filesystem,
               size_gb, used_gb, avail_gb, used_pct, captured_at
          FROM eis.fact_it_disk_usage
         WHERE captured_at = (SELECT MAX(captured_at) FROM eis.fact_it_disk_usage)
    """
    params = {}
    if server:
        sql += " AND (UPPER(server_key) = UPPER(%(server)s) OR UPPER(server_label) LIKE UPPER(%(server_like)s))"
        params["server"] = server
        params["server_like"] = f"%{server}%"
    if min_used_pct is not None:
        sql += " AND used_pct >= %(min_used_pct)s"
        params["min_used_pct"] = min_used_pct
    sql += " ORDER BY used_pct DESC"
    return _query(sql, params)


def get_oracle_activity() -> list[dict]:
    """Latest Oracle session counts and concurrent-request backlog."""
    sql = """
        SELECT active_sessions, inactive_sessions, blocked_sessions,
               pending_requests, running_requests, top_wait_event, captured_at
          FROM eis.fact_it_oracle_activity
         ORDER BY captured_at DESC
         LIMIT 1
    """
    return _query(sql, {})


def get_daily_sales(year: int, month: str = None) -> list[dict]:
    """Daily Sales grid — one row per working day, from eis.fact_daily_sales.

    Working days a month never reached are dropped at ETL time rather than
    returned as zeros, so a short month is short rather than padded with days
    that look like they sold nothing.
    """
    sql = """
        SELECT fiscal_year, month_name, month_num, working_day,
               sales, acc, target, as_of
          FROM eis.fact_daily_sales
         WHERE fiscal_year = %(year)s
    """
    params = {"year": year}
    if month:
        sql += " AND LOWER(month_name) = LOWER(%(month)s)"
        params["month"] = month
    sql += " ORDER BY month_num, working_day"
    return _query(sql, params)


_DISPATCH = {
    "get_sales_performance": get_sales_performance,
    "get_production_performance": get_production_performance,
    "get_budget_vs_actual": get_budget_vs_actual,
    "get_financial_summary": get_financial_summary,
    "get_cogs_performance": get_cogs_performance,
    "get_ar_ap_summary": get_ar_ap_summary,
    "get_inventory_summary": get_inventory_summary,
    "get_employee_headcount": get_employee_headcount,
    "get_purchasing_performance": get_purchasing_performance,
    "get_purchase_order_detail": get_purchase_order_detail,
    "get_sales_order_detail": get_sales_order_detail,
    "get_employee_directory": get_employee_directory,
    "get_daily_sales": get_daily_sales,
    "get_tablespace_usage": get_tablespace_usage,
    "get_tablespace_trend": get_tablespace_trend,
    "get_server_resources": get_server_resources,
    "get_disk_usage": get_disk_usage,
    "get_oracle_activity": get_oracle_activity,
}


def execute_tool(tool_name: str, arguments: dict) -> list[dict]:
    fn = _DISPATCH.get(tool_name)
    if fn is None:
        raise ValueError(f"Unknown tool: {tool_name}")
    return fn(**arguments)
