"""
EIS Tool Calling — Oracle EBS Data Chat
─────────────────────────────────────────
The chat model never sees or writes raw SQL. Every tool below maps to one
predefined, parameterized SELECT against Postgres EIS (172.21.2.209:5433,
schema `eis`, ETL'd from Oracle EBS) run as a dedicated `chat_readonly`
role that only has SELECT on schema `eis` — even a prompt-injected or
hallucinated argument can't turn into a write, because the DB user itself
can't write. See sumber/AI_Chat_Implementation_Guide.md section 5.
"""
import re
import psycopg2
from psycopg2.extras import RealDictCursor
from app.config import get_settings

settings = get_settings()

EIS_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_sales_performance",
            "description": "Ambil data performa penjualan (budget plan vs aktual vs tahun lalu) per periode, opsional difilter per produk atau tipe bisnis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "description": "Periode fiskal, format YYYY-MM, contoh 2026-06"},
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
                    "period": {"type": "string", "description": "Periode fiskal, format YYYY-MM, contoh 2026-06"},
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
                    "period": {"type": "string", "description": "Periode fiskal, format YYYY-MM, contoh 2026-06"},
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
                    "period": {"type": "string", "description": "Periode fiskal, format YYYY-MM, contoh 2026-06"},
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
                    "period": {"type": "string", "description": "Periode fiskal, format YYYY-MM, contoh 2026-06"},
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
                    "period": {"type": "string", "description": "Periode fiskal, format YYYY-MM, contoh 2026-06"},
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
                    "period": {"type": "string", "description": "Periode fiskal, format YYYY-MM, contoh 2026-06"},
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
                    "period": {"type": "string", "description": "Periode fiskal, format YYYY-MM, contoh 2026-06"},
                    "material_type": {"type": "string", "description": "Opsional. Salah satu dari: Direct, Indirect, Unclassified"},
                },
                "required": ["period"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_purchase_order_detail",
            "description": "Cari data PO (Purchase Order) individual — nomor PO, item, harga — berdasarkan supplier, kode item, dan/atau nomor PO. Untuk pertanyaan 'PO apa saja dari supplier X', 'PO nomor berapa untuk item Y', bukan sekadar total/trend (untuk itu pakai get_purchasing_performance).",
            "parameters": {
                "type": "object",
                "properties": {
                    "supplier_name": {"type": "string", "description": "Opsional. Nama supplier (partial match), contoh IFORTE"},
                    "item_code": {"type": "string", "description": "Opsional. Kode item Oracle"},
                    "po_number": {"type": "string", "description": "Opsional. Nomor PO (partial match)"},
                    "period": {"type": "string", "description": "Opsional. Periode fiskal, format YYYY-MM, contoh 2026-06"},
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
            "description": "Cari daftar karyawan (nama, posisi, department, team, tanggal masuk, status) — untuk pertanyaan 'siapa saja di tim X' atau cari data karyawan tertentu, bukan sekadar jumlah headcount.",
            "parameters": {
                "type": "object",
                "properties": {
                    "department": {"type": "string", "description": "Opsional. Salah satu dari: Administration, Sales & Marketing, Strategy & Development, Plant"},
                    "team": {"type": "string", "description": "Opsional. Nama tim, contoh IT, HRGA, Purchasing, Accounting"},
                    "full_name": {"type": "string", "description": "Opsional. Cari berdasarkan nama (partial match)"},
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
                    "period": {"type": "string", "description": "Periode fiskal, format YYYY-MM, contoh 2026-06"},
                    "dept_group": {"type": "string", "description": "Opsional. Grup departemen, contoh Plant Direct, SM, Admin"},
                },
                "required": ["period"],
            },
        },
    },
]

_PERIOD_RE = re.compile(r"^(\d{4})-(\d{1,2})$")


def _parse_period(period: str) -> tuple[int, int]:
    m = _PERIOD_RE.match((period or "").strip())
    if not m:
        raise ValueError(f"Invalid period format '{period}' — expected YYYY-MM")
    fiscal_year, period_num = int(m.group(1)), int(m.group(2))
    if not (1 <= period_num <= 12):
        raise ValueError(f"Invalid month in period '{period}'")
    return fiscal_year, period_num


def _get_conn():
    return psycopg2.connect(settings.eis_database_url)


def _query(sql: str, params: dict) -> list[dict]:
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
    finally:
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
        WHERE per.fiscal_year = %(fy)s AND per.period_num = %(pnum)s
          AND (%(product_code)s IS NULL OR dp.product_code = %(product_code)s)
          AND (%(business_type)s IS NULL OR fs.business_type = %(business_type)s)
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
        WHERE per.fiscal_year = %(fy)s AND per.period_num = %(pnum)s
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
        WHERE per.fiscal_year = %(fy)s AND per.period_num = %(pnum)s
          AND (%(dept_group)s IS NULL OR fb.dept_group = %(dept_group)s)
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
        WHERE per.fiscal_year = %(fy)s AND per.period_num = %(pnum)s
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
        WHERE per.fiscal_year = %(fy)s AND per.period_num = %(pnum)s
          AND (%(product_code)s IS NULL OR dp.product_code = %(product_code)s)
          AND (%(business_type)s IS NULL OR fc.business_type = %(business_type)s)
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
        WHERE per.fiscal_year = %(fy)s AND per.period_num = %(pnum)s
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
        WHERE per.fiscal_year = %(fy)s AND per.period_num = %(pnum)s
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
        WHERE per.fiscal_year = %(fy)s AND per.period_num = %(pnum)s
          AND (%(material_type)s IS NULL OR p.material_type = %(material_type)s)
        ORDER BY p.material_type
        """,
        {"fy": fy, "pnum": pnum, "material_type": material_type},
    )


def get_purchase_order_detail(
    supplier_name: str = None, item_code: str = None, po_number: str = None, period: str = None,
) -> list[dict]:
    """Line-item PO search — backed by eis.fact_po_line (etl_po_lines),
    the same table Purchasing History/Price Analysis read from. Added so
    the chatbot can answer "which POs from supplier X" questions that
    get_purchasing_performance's aggregate-only shape never could."""
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
          AND (%(item_code)s    IS NULL OR item_code = %(item_code)s)
          AND (%(po_number)s    IS NULL OR po_number ILIKE %(po_like)s)
          AND (%(fy)s   IS NULL OR EXTRACT(YEAR FROM creation_date) = %(fy)s)
          AND (%(pnum)s IS NULL OR EXTRACT(MONTH FROM creation_date) = %(pnum)s)
        ORDER BY creation_date DESC
        LIMIT 50
        """,
        {
            "supplier_name": supplier_name, "supplier_like": f"%{supplier_name}%" if supplier_name else None,
            "item_code": item_code,
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
          AND (%(item_code)s      IS NULL OR item_code = %(item_code)s)
          AND (%(order_number)s   IS NULL OR order_number ILIKE %(order_like)s)
          AND (%(business_type)s  IS NULL OR business_type = %(business_type)s)
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


def get_employee_directory(department: str = None, team: str = None, full_name: str = None) -> list[dict]:
    return _query(
        """
        SELECT employee_number, full_name, department, division, team, position_title,
               hire_date, employment_status
        FROM eis.dim_employee
        WHERE (%(department)s IS NULL OR department = %(department)s)
          AND (%(team_like)s IS NULL OR team ILIKE %(team_like)s)
          AND (%(name_like)s IS NULL OR full_name ILIKE %(name_like)s)
        ORDER BY department, team, full_name
        LIMIT 100
        """,
        {
            "department": department,
            "team_like": f"%{team}%" if team else None,
            "name_like": f"%{full_name}%" if full_name else None,
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
        WHERE per.fiscal_year = %(fy)s AND per.period_num = %(pnum)s
          AND (%(dept_group)s IS NULL OR e.dept_group = %(dept_group)s)
        """,
        {"fy": fy, "pnum": pnum, "dept_group": dept_group},
    )


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
}


def execute_tool(tool_name: str, arguments: dict) -> list[dict]:
    fn = _DISPATCH.get(tool_name)
    if fn is None:
        raise ValueError(f"Unknown tool: {tool_name}")
    return fn(**arguments)
