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
}


def execute_tool(tool_name: str, arguments: dict) -> list[dict]:
    fn = _DISPATCH.get(tool_name)
    if fn is None:
        raise ValueError(f"Unknown tool: {tool_name}")
    return fn(**arguments)
