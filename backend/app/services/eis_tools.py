"""
EIS Tool Calling — Oracle EBS Data Chat
─────────────────────────────────────────
The chat model never sees or writes raw SQL. Every tool below maps to one
predefined, parameterized SELECT against schema `eis` in the main
ckdo_dashboard Postgres (ETL'd from Oracle EBS), run as a dedicated `chat_readonly`
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

# Setiap tool yang mengembalikan quantity WAJIB ikut mengembalikan uom.
#
# Bukan soal kerapian. Pada 2026-09-24 pembelian Bortezomib dilaporkan sebagai
# "100 kg" padahal satuannya GR — meleset seribu kali. Kolom uom ada di tabel,
# hanya tidak ikut di-SELECT, jadi model tidak punya satuan dan menuliskan yang
# paling masuk akal menurutnya. Satuan di fact_po_line beragam (PKG, PCS, BOX,
# BTL, PAK, UNT, GR, VL), jadi menebak hampir selalu salah, dan angka bersatuan
# salah terbaca seperti angka yang benar.
#
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
            "description": "Cari data PO (Purchase Order) individual per baris — sama persis dengan Detail View laporan Purchase History di dashboard. Setiap baris berisi: nomor & tanggal PR, requestor, nomor PO, tanggal PO, status, item (kode, deskripsi, kategori, item type, material type, negara asal), supplier, organisasi, mata uang, satuan (uom), delivery date, qty, harga per unit, amount, amount IDR, qty diterima (received_qty), nomor & tanggal receipt terakhir, qty outstanding, payment term (termin pembayaran), dan buyer. Cari berdasarkan supplier, nama barang, kode item, nomor PO, periode, material type, kategori, buyer, requestor, dan/atau negara asal. Untuk pertanyaan 'PO apa saja dari supplier X', 'payment term PO Y', 'sudah diterima belum', 'siapa requestor/buyer-nya' — bukan sekadar total/trend (untuk itu pakai get_purchasing_performance). Maksimal 50 baris terbaru per panggilan; persempit filter kalau perlu lebih.",
            "parameters": {
                "type": "object",
                "properties": {
                    "supplier_name": {"type": "string", "description": "Opsional. Nama supplier (partial match), contoh IFORTE"},
                    "item_code": {"type": "string", "description": "Opsional. Kode item Oracle persis, contoh CKD21R0303. Jangan diisi nama bahan \u2014 untuk itu pakai item_name."},
                    "item_name": {"type": "string", "description": "Opsional. Nama atau deskripsi barang (partial match), contoh Bortezomib, Paracetamol, LABEL. Pakai ini kalau yang disebut pengguna adalah nama bahan/barang, bukan kode."},
                    "po_number": {"type": "string", "description": "Opsional. Nomor PO (partial match)"},
                    "period": {"type": "string", "description": "Opsional. Periode fiskal: YYYY-MM untuk satu bulan (contoh 2026-06), atau YYYY untuk satu tahun penuh (contoh 2025). Pakai bentuk tahun untuk pertanyaan sepanjang tahun \u2014 jangan memanggil tool ini dua belas kali."},
                    "material_type": {"type": "string", "description": "Opsional. Tipe material, dicocokkan sebagai awalan: DIRECT MATERIAL atau INDIRECT MATERIAL."},
                    "category": {"type": "string", "description": "Opsional. Kategori item persis, contoh API, EXCIPIENT, PRIMER, SEKUNDER, LIQUID."},
                    "buyer_name": {"type": "string", "description": "Opsional. Nama buyer (partial match)."},
                    "requestor": {"type": "string", "description": "Opsional. User pembuat PR / requestor (partial match), contoh MEGA."},
                    "country_of_origin": {"type": "string", "description": "Opsional. Negara asal barang (partial match), contoh INDIA, CHINA."},
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
            "description": "Cari daftar / total karyawan (nama, posisi, department, team, tanggal masuk, status, tanggal & alasan resign, TANGGAL LAHIR) — untuk pertanyaan 'siapa saja di tim X', cari data karyawan tertentu, 'berapa total karyawan resign/aktif saat ini' (hitung dari jumlah baris hasil, employment_status='Resign' untuk yang sudah keluar, 'Active' untuk yang masih bekerja), 'kapan/kenapa si X resign' (pakai field resign_date dan resign_reason di hasilnya — SISTEM INI MENYIMPAN tanggal & alasan resign, jangan bilang tidak ada), atau pertanyaan ULANG TAHUN / TANGGAL LAHIR (pakai field date_of_birth; untuk 'siapa yang ulang tahun bulan ini/bulan Maret' pakai parameter birth_month — SISTEM INI MENYIMPAN tanggal lahir, jangan bilang tidak ada). Sebagian kecil karyawan tanggal lahirnya kosong; sebutkan itu bila relevan, jangan diartikan sebagai tidak ada data sama sekali.",
            "parameters": {
                "type": "object",
                "properties": {
                    "department": {"type": "string", "description": "Opsional. Salah satu dari: Administration, Sales & Marketing, Strategy & Development, Plant"},
                    "team": {"type": "string", "description": "Opsional. Nama tim, contoh IT, HRGA, Purchasing, Accounting"},
                    "full_name": {"type": "string", "description": "Opsional. Cari berdasarkan nama (partial match)"},
                    "employment_status": {"type": "string", "description": "Opsional. 'Active' (masih bekerja) atau 'Resign' (sudah keluar) — pakai ini untuk pertanyaan total/daftar karyawan resign atau aktif"},
                    "birth_month": {"type": "integer", "description": "Opsional. Bulan lahir 1-12 — untuk pertanyaan 'siapa yang ulang tahun bulan ini' atau 'ulang tahun bulan Maret'. Menyaring berdasarkan bulan saja, tahun lahir diabaikan."},
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
            "description": "Kondisi CPU, memori, swap, load, dan uptime server yang terdaftar di Server Control (mis. Oracle EBS - Database, Oracle EBS - Application, AI Server Engine). Jika argumen server diisi (nama atau IP), data server itu diambil LANGSUNG saat ini lalu disimpan. Tanpa argumen mengembalikan snapshot terakhir tiap server terjadwal. captured_at = waktu pengukuran; baris berisi 'note' menjelaskan server yang tidak bisa diambil.",
            "parameters": {
                "type": "object",
                "properties": {
                    "server": {"type": "string", "description": "Nama server di Server Control (boleh sebagian, mis. 'database', 'ai server engine') atau IP-nya, mis. '172.21.2.27'. Memicu pengambilan data langsung."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_disk_usage",
            "description": "Pemakaian filesystem (storage) per mount point di server yang terdaftar di Server Control. Jika argumen server diisi (nama atau IP), datanya diambil LANGSUNG saat ini lalu disimpan. Gunakan min_used_pct untuk mencari partisi yang hampir penuh.",
            "parameters": {
                "type": "object",
                "properties": {
                    "server": {"type": "string", "description": "Nama server di Server Control (boleh sebagian, mis. 'database', 'ai server engine') atau IP-nya, mis. '172.21.2.27'. Memicu pengambilan data langsung."},
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
    {
        "type": "function",
        "function": {
            "name": "get_server_top_processes",
            "description": "Proses teratas (8 besar) menurut pemakaian CPU atau memori di server yang terdaftar di Server Control — untuk pertanyaan 'proses apa yang bikin CPU/memori tinggi'. Jika argumen server diisi (nama atau IP), datanya diambil LANGSUNG saat ini lalu disimpan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "server": {"type": "string", "description": "Nama server di Server Control (boleh sebagian, mis. 'database', 'ai server engine') atau IP-nya, mis. '172.21.2.27'. Memicu pengambilan data langsung."},
                    "sort_by": {"type": "string", "enum": ["cpu", "mem"], "description": "Urutkan menurut CPU (default) atau memori."},
                },
                "required": [],
            },
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


# dim_product.product_code holds Oracle's numeric item id (e.g. 206043) and
# product_name holds the item code people use (e.g. EXP05BOR03), so the
# product filter matches either — exactly, never as a prefix: a partial code
# would match other products. Before 2026-09-30 it matched product_code only,
# and every filter by the code users actually know returned no rows.
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
          AND (%(product_code)s IS NULL OR UPPER(dp.product_code) = UPPER(%(product_code)s)
               OR UPPER(dp.product_name) = UPPER(%(product_code)s))
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
        SELECT dp.product_code, dp.product_name, dp.business_type,
               fc.sales_amount, fc.cogs_total, fc.ebit_amount,
               CASE WHEN fc.sales_amount > 0
                    THEN round((fc.ebit_amount / fc.sales_amount * 100)::numeric, 1)
               END AS ebit_pct
        FROM eis.fact_cogs fc
        JOIN eis.dim_period per ON per.id = fc.period_id
        JOIN eis.dim_product dp ON dp.id = fc.product_id
        WHERE per.fiscal_year = %(fy)s AND (%(pnum)s IS NULL OR per.period_num = %(pnum)s)
          AND (%(product_code)s IS NULL OR UPPER(dp.product_code) = UPPER(%(product_code)s)
               OR UPPER(dp.product_name) = UPPER(%(product_code)s))
          AND (%(business_type)s IS NULL OR UPPER(dp.business_type) LIKE UPPER(%(business_type)s) || '%%')
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
    po_number: str = None, period: str = None, material_type: str = None,
    category: str = None, buyer_name: str = None, requestor: str = None,
    country_of_origin: str = None,
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
    exactly.

    Returns every column of the Purchase History Detail View (same order),
    so anything visible on the dashboard can be answered here — payment
    term, PR/requestor, receipt number/date and qty outstanding were
    missing before and the chat reported them as unavailable."""
    fy = pnum = None
    if period:
        fy, pnum = _parse_period(period)

    def _like(v):
        return f"%{v}%" if v else None

    return _query(
        """
        SELECT pr_number, pr_date, requestor, po_number, line_num, creation_date AS po_date,
               closure_status, item_code, item_description, category, item_type, material_type,
               country_of_origin, supplier_name, organization_name, currency_code, uom,
               delivery_date, quantity, unit_price, amount_orig, amount_idr, received_qty,
               receipt_number, receipt_date, qty_outstanding, payment_term, buyer_name
        FROM eis.fact_po_line
        WHERE (%(supplier_name)s IS NULL OR supplier_name ILIKE %(supplier_like)s)
          AND (%(item_code)s    IS NULL OR UPPER(item_code) = UPPER(%(item_code)s))
          AND (%(item_name)s    IS NULL OR item_description ILIKE %(item_name_like)s)
          AND (%(po_number)s    IS NULL OR po_number ILIKE %(po_like)s)
          AND (%(material_type)s IS NULL OR UPPER(material_type) LIKE UPPER(%(material_type)s) || '%%')
          AND (%(category)s     IS NULL OR UPPER(category) = UPPER(%(category)s))
          AND (%(buyer_name)s   IS NULL OR buyer_name ILIKE %(buyer_like)s)
          AND (%(requestor)s    IS NULL OR requestor ILIKE %(requestor_like)s)
          AND (%(country)s      IS NULL OR country_of_origin ILIKE %(country_like)s)
          AND (%(fy)s   IS NULL OR EXTRACT(YEAR FROM creation_date) = %(fy)s)
          AND (%(pnum)s IS NULL OR EXTRACT(MONTH FROM creation_date) = %(pnum)s)
        ORDER BY creation_date DESC, po_number, line_num
        LIMIT 50
        """,
        {
            "supplier_name": supplier_name, "supplier_like": _like(supplier_name),
            "item_code": item_code,
            "item_name": item_name, "item_name_like": _like(item_name),
            "po_number": po_number, "po_like": _like(po_number),
            "material_type": material_type, "category": category,
            "buyer_name": buyer_name, "buyer_like": _like(buyer_name),
            "requestor": requestor, "requestor_like": _like(requestor),
            "country": country_of_origin, "country_like": _like(country_of_origin),
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
               business_type, currency_code, uom, quantity, unit_selling_price,
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


def get_employee_directory(department: str = None, team: str = None, full_name: str = None,
                           employment_status: str = None, birth_month: int = None) -> list[dict]:
    # birth_month menyaring BULAN saja, tahun diabaikan: pertanyaan ulang tahun
    # selalu "siapa bulan ini", tidak pernah "siapa yang lahir Maret 1990".
    # Diurutkan per tanggal saat menyaring bulan, supaya jawabannya langsung
    # terbaca sebagai kalender, bukan daftar per departemen.
    return _query(
        """
        SELECT employee_number, full_name, department, division, team, position_title,
               hire_date, employment_status, resign_date, resign_reason, date_of_birth
        FROM eis.dim_employee
        WHERE (%(department)s IS NULL OR UPPER(department) LIKE UPPER(%(department)s) || '%%')
          AND (%(team_like)s IS NULL OR team ILIKE %(team_like)s)
          AND (%(name_like)s IS NULL OR full_name ILIKE %(name_like)s)
          AND (%(employment_status)s IS NULL OR UPPER(employment_status) LIKE UPPER(%(employment_status)s) || '%%')
          AND (%(birth_month)s IS NULL
               OR EXTRACT(MONTH FROM date_of_birth) = %(birth_month)s)
        ORDER BY
            CASE WHEN %(birth_month)s IS NULL THEN NULL
                 ELSE EXTRACT(DAY FROM date_of_birth) END,
            department, team, full_name
        LIMIT 500
        """,
        {
            "department": department,
            "team_like": f"%{team}%" if team else None,
            "name_like": f"%{full_name}%" if full_name else None,
            "employment_status": employment_status,
            "birth_month": birth_month,
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


# Server rows are written per server — by the 15-minute ETL and by every
# refresh of the Server Process / Storage Monitoring pages — so "the newest
# snapshot" is the newest one PER SERVER, not the table's single MAX
# (captured_at), which would drop every server but the last one refreshed.
# A server not seen for a day (monitoring switched off) drops out.
def _latest_per_server(table: str, extra_key: str = "") -> str:
    return f"""
        JOIN (SELECT server_key, {extra_key} MAX(captured_at) AS latest_at
                FROM eis.{table}
               WHERE captured_at >= NOW() - INTERVAL '1 day'
               GROUP BY server_key {', ' + extra_key.rstrip(', ') if extra_key else ''}) l
          ON l.server_key = t.server_key AND l.latest_at = t.captured_at
             {'AND l.' + extra_key.rstrip(', ') + ' = t.' + extra_key.rstrip(', ') if extra_key else ''}
    """


def _live(server: str, kind: str) -> dict | None:
    """A question that names a server triggers a fresh SSH reading of it
    (stored with source='cochat') before the snapshot is read, so the answer
    is about now and any Server Control server can be asked about — not only
    the ones in the 15-minute schedule. Without a server name the tools read
    the stored snapshots only; polling every host per question would be slow
    and is what the schedule is for."""
    if not server:
        return None
    try:
        from app.services.it_service import ServerMonitorService
        return ServerMonitorService().refresh_for_chat(server, kind)
    except Exception as e:
        return {"keys": [], "notes": [{"note": f"Live poll unavailable: {e}"}]}


def _with_live(rows: list[dict], live: dict | None, server: str) -> list[dict]:
    if live is None:
        return rows
    if not live["keys"]:
        return [{"note": f"No server matching '{server}' in Server Control."}]
    return rows + live["notes"]


def _server_filter(server: str, params: dict, live: dict | None = None) -> str:
    if live and live["keys"]:
        params["server_keys"] = live["keys"]
        return " AND t.server_key = ANY(%(server_keys)s)"
    if not server:
        return ""
    params["server"] = server
    params["server_like"] = f"%{server}%"
    return (" AND (UPPER(t.server_key) = UPPER(%(server)s) OR t.server_ip = %(server)s"
            " OR UPPER(t.server_label) LIKE UPPER(%(server_like)s)"
            " OR UPPER(t.server_key) LIKE UPPER(%(server_like)s))")


def get_server_resources(server: str = None) -> list[dict]:
    """Latest CPU / memory / swap / load / uptime per server."""
    live = _live(server, "metrics")
    params = {}
    sql = f"""
        SELECT t.server_key, t.server_label, t.server_ip, t.status,
               t.cpu_pct, t.cpu_count, t.memory_pct, t.memory_used_gb, t.memory_total_gb,
               t.swap_pct, t.load_1, t.uptime, t.error_message, t.captured_at
          FROM eis.fact_it_server_metrics t
          {_latest_per_server("fact_it_server_metrics")}
         WHERE TRUE {_server_filter(server, params, live)}
         ORDER BY t.server_label
    """
    return _with_live(_query(sql, params), live, server)


def get_server_top_processes(server: str = None, sort_by: str = "cpu") -> list[dict]:
    """Latest top-8 processes per server, by CPU or by memory."""
    sort_by = "mem" if (sort_by or "").lower().startswith("mem") else "cpu"
    live = _live(server, "processes")
    params = {"sort_by": sort_by}
    sql = f"""
        SELECT t.server_key, t.server_label, t.server_ip, t.sort_by, t.rank,
               t.os_user, t.pid, t.cpu_pct, t.mem_pct, t.command, t.captured_at
          FROM eis.fact_it_top_process t
          {_latest_per_server("fact_it_top_process", "sort_by, ")}
         WHERE t.sort_by = %(sort_by)s {_server_filter(server, params, live)}
         ORDER BY t.server_label, t.rank
    """
    return _with_live(_query(sql, params), live, server)


def get_disk_usage(server: str = None, min_used_pct: float = None) -> list[dict]:
    """Latest filesystem usage per mount point, optionally filtered."""
    live = _live(server, "disk")
    params = {}
    sql = f"""
        SELECT t.server_key, t.server_label, t.server_ip, t.mount_point, t.filesystem,
               t.size_gb, t.used_gb, t.avail_gb, t.used_pct, t.captured_at
          FROM eis.fact_it_disk_usage t
          {_latest_per_server("fact_it_disk_usage")}
         WHERE TRUE {_server_filter(server, params, live)}
    """
    if min_used_pct is not None:
        sql += " AND t.used_pct >= %(min_used_pct)s"
        params["min_used_pct"] = min_used_pct
    sql += " ORDER BY t.used_pct DESC"
    return _with_live(_query(sql, params), live, server)


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
    "get_server_top_processes": get_server_top_processes,
}


def execute_tool(tool_name: str, arguments: dict) -> list[dict]:
    fn = _DISPATCH.get(tool_name)
    if fn is None:
        raise ValueError(f"Unknown tool: {tool_name}")
    return fn(**arguments)


# ── Exact totals next to the rows ─────────────────────────────────────────────
# A year question ("total pembelian 2025 per material type") returns one row
# per month per category, and the model had to add them up itself. On
# 2026-09-30 both Sonnet 5 and Haiku 4.5 got it wrong from the same 26 rows:
# one dropped the "Unclassified" rows (Rp 190,45 M instead of 207,12 M), the
# other mis-added the PO counts. So the sum is done here, exactly, and handed
# over as `totals`; the prompt tells the model to quote it rather than add.
#
# Only flows are summed. Balances and ratios (AR/AP days, inventory days,
# headcount, cash balances) are month-end positions — adding twelve of them
# gives a number that means nothing — so those tools get a note instead.

# tool -> (group-by column or None, additive columns, derived ratios,
#          column groups are ordered by — largest first; None = row order)
_TOTALS = {
    "get_purchasing_performance": ("material_type", ["po_count", "po_value"], {}, "po_value"),
    "get_sales_performance": ("business_type", ["bp_amount", "actual_amount", "prior_year_actual"],
                              {"variance_vs_budget": ("actual_amount", "-", "bp_amount")}, "actual_amount"),
    "get_cogs_performance": ("business_type", ["sales_amount", "cogs_total", "ebit_amount"],
                             {"ebit_pct": ("ebit_amount", "%", "sales_amount")}, "sales_amount"),
    "get_production_performance": ("segment", ["bp_qty", "actual_qty", "yield_qty"],
                                   {"achievement_pct": ("actual_qty", "%", "bp_qty")}, "actual_qty"),
    "get_budget_vs_actual": ("dept_group", ["bp_amount", "actual_amount"],
                             {"variance": ("actual_amount", "-", "bp_amount")}, "actual_amount"),
    "get_financial_summary": (None, ["net_profit_bp", "net_profit_actual", "cf_cash_in_actual",
                                     "cf_cash_out_actual"], {}, None),
    # Rows arrive in calendar order; keep it.
    "get_daily_sales": ("month_name", ["sales"], {}, None),
}
# Tables that carry their own subtotal rows next to the detail. fact_sales has
# one row per business type with no product (the official total) plus the
# per-product rows that break it down; adding both doubles the sales. When the
# subtotal rows are present the totals use only them.
_SUBTOTAL_ROWS = {
    "get_sales_performance": (lambda r: r.get("product_code") is None,
                              "Rows in data without product_code are the official business-type totals; the "
                              "product rows break them down. Never add both kinds of rows together."),
}

# Money columns whose unit has been checked against the table contents (see
# SYSTEM_PROMPT in oracle_chat_service). For these the totals also carry the
# unit and a ready-to-quote Indonesian amount, because models still slip on
# the conversion: Sonnet 5 wrote "Rp 23,22 juta" for 23.218,55 juta
# (= Rp 23,2 miliar). get_budget_vs_actual is deliberately absent — the
# prompt says juta but the loaded rows look like full rupiah; unverified.
_MONEY_UNIT = {
    "get_purchasing_performance": ("IDR", 1, ["po_value"]),
    "get_financial_summary": ("IDR", 1, ["net_profit_bp", "net_profit_actual", "cf_cash_in_actual",
                                         "cf_cash_out_actual"]),
    "get_sales_performance": ("juta IDR", 1e6, ["bp_amount", "actual_amount", "prior_year_actual",
                                                "variance_vs_budget"]),
    "get_cogs_performance": ("juta IDR", 1e6, ["sales_amount", "cogs_total", "ebit_amount"]),
}


def rupiah_text(idr: float) -> str:
    """Rp 207,12 miliar / Rp 691,90 juta / Rp 1,20 triliun — Indonesian decimal comma."""
    sign = "-" if idr < 0 else ""
    a = abs(idr)
    for div, word in ((1e12, "triliun"), (1e9, "miliar"), (1e6, "juta")):
        if a >= div:
            return f"{sign}Rp {a / div:,.2f} {word}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sign}Rp {a:,.0f}".replace(",", ".")


def _add_text(d: dict, factor: float, cols: list[str]) -> dict:
    for c in cols:
        if isinstance(d.get(c), (int, float)):
            d[c + "_text"] = rupiah_text(d[c] * factor)
    return d


_NOT_ADDITIVE = {
    "get_ar_ap_summary": "Days and average balances per month — do not add months together; quote the "
                         "month asked for, or the latest month for a year question.",
    "get_inventory_summary": "Inventory days and average balances per month — do not add months together.",
    "get_employee_headcount": "Headcount is a month-end count — do not add months together; for a year "
                              "question use the latest month. resigned_cumulative is already cumulative.",
}


def _num(v):
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _derive(acc: dict, derived: dict) -> dict:
    for name, (a, op, b) in derived.items():
        if op == "-":
            acc[name] = round(acc[a] - acc[b], 2)
        elif op == "%":
            acc[name] = round(acc[a] / acc[b] * 100, 1) if acc[b] else None
    return acc


def summarize(tool_name: str, rows: list[dict]) -> dict | None:
    """Exact totals for `rows`, grouped by the tool's category column, plus a
    grand total — or a note for balance/ratio tools. None for tools where a
    sum means nothing (detail lists, snapshots) or when there are no rows."""
    if tool_name in _NOT_ADDITIVE:
        return {"note": _NOT_ADDITIVE[tool_name]} if rows else None
    spec = _TOTALS.get(tool_name)
    if not spec or not rows:
        return None
    group_col, cols, derived, order_by = spec
    sub = _SUBTOTAL_ROWS.get(tool_name)
    extra_note = ""
    if sub:
        subtotal_rows = [r for r in rows if sub[0](r)]
        if subtotal_rows:
            rows = subtotal_rows
        extra_note = " " + sub[1]
    grand = {c: 0.0 for c in cols}
    groups: dict = {}
    for r in rows:
        key = (r.get(group_col) or "Unclassified") if group_col else None
        g = groups.setdefault(key, {c: 0.0 for c in cols} | {"rows": 0})
        g["rows"] += 1
        for c in cols:
            v = _num(r.get(c))
            g[c] += v
            grand[c] += v
    def fmt(d):
        return {k: (int(v) if isinstance(v, float) and v.is_integer() else round(v, 2) if isinstance(v, float)
                    else v) for k, v in d.items()}
    out = {"note": "Exact sums of every row returned (all months in the period). Quote these for totals "
                   "instead of adding the rows yourself. Units are the same as the columns in data." + extra_note}
    if group_col:
        items = list(groups.items())
        if order_by:
            items.sort(key=lambda kv: -abs(kv[1][order_by]))
        out["by_" + group_col] = [{group_col: k, **fmt(_derive(dict(v), derived))} for k, v in items]
    out["grand_total"] = fmt(_derive(dict(grand) | {"rows": len(rows)}, derived))
    money = _MONEY_UNIT.get(tool_name)
    if money:
        unit, factor, mcols = money
        out["unit"] = unit
        out["note"] += (f" Money columns are in {unit}; each has a *_text twin with the amount already "
                        "converted — quote that text as-is.")
        for g in out.get("by_" + group_col, []) if group_col else []:
            _add_text(g, factor, mcols)
        _add_text(out["grand_total"], factor, mcols)
    return out
