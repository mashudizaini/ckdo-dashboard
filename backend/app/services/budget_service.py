"""
Budget Monitoring Service
─────────────────────────────────────────
Query langsung ke Oracle EBS 12.2.8 — pola identik dengan ITService & PurchasingService.
Layout & rumus meniru persis Oracle EBS "Funds Available Inquiry" /
"Period Balances (YTDE)" drilldown — supaya angkanya selalu bisa dicocokkan
langsung dengan yang dilihat user di Oracle client.

COA Structure CKD Otto:
  segment3 = CKDO_GL_COA_DEPARTMENT  → department (parameter, tidak di-hardcode)
  segment4 = natural account           → kode akun

Sumber data (semua dari GL_BALANCES, per akun per periode/bulan):
  actual_flag='B'  → Budget
  actual_flag='E'  → Encumbrance
  actual_flag='A'  → Actual (SEMUA sumber posting: AP Invoice, payroll, jurnal manual, dll)

Rumus (sama di get_summary & get_account_detail):
  Funds Available = Budget − Encumbrance − Actual

get_summary: parameter `month` = Year-To-Date SAMPAI DENGAN bulan itu (Oracle
"Year To Date Extended"), bukan Period-To-Date bulan itu saja; kosong = satu
tahun penuh. Parameter `account` opsional untuk filter ke satu akun.

get_account_detail: pecahan per periode (satu baris per bulan, dipotong s.d.
parameter `month` kalau diisi) dari rumus yang sama, meniru Oracle "Period
Balances (YTDE)". AP_EXPENSE_REPORT_LINES + PO_REQUISITION_LINES_ALL
(_query_expense_report_items / _query_purchase_requisition_items) disertakan
per periode sebagai daftar transaksi pendukung Actual (klik untuk lihat) —
untuk transparansi sumber saja, BUKAN komponen rumus Funds Available (Actual
GL sudah mencakup lebih banyak sumber daripada dua tabel itu).

CATATAN PENTING — kenapa angka Budget/Encumbrance kadang beda dari layar
Oracle live: dikonfirmasi langsung ke Oracle PROD (2026-08-12, akun 611311)
bahwa GL_BALANCES('B') HANYA mengakumulasi jurnal budget yang statusnya
POSTED ('P') — sementara layar Oracle "Funds Available Inquiry"/"Period
Balances" milik CKD Otto ikut menghitung jurnal budget yang masih UNPOSTED
('U') kalau ada (mis. akun 611311 periode MAR-26: GL_BALANCES('B') = Rp
1.609.651, tapi ada 2 baris jurnal "CJE: Budget..." berstatus U senilai
netto +Rp 530.122 yang TIDAK ikut GL_BALANCES — begitu ditambahkan
manual, hasilnya persis Rp 2.139.773, cocok dengan layar Oracle).
Masalahnya: draft/jurnal unposted TIDAK SELALU berarti "pending, belum
sempat diposting" — ditemukan juga kasus draft unposted yang ternyata
DUPLIKAT dari jurnal yang sudah diposting terpisah (akun sama, periode
JUL-26: 2 baris unposted identik yang sudah "digantikan" oleh 1 baris
posted senilai sama) — kalau ikut dijumlah at-face-value, hasilnya malah
salah (kehitung 3x). Karena tidak ada cara pasti membedakan "draft yang
masih perlu diposting" dari "draft basi yang sudah digantikan" hanya dari
data historis, get_summary/get_account_detail TETAP pakai GL_BALANCES
(posted-only) sebagai angka utama — ini sudah tervalidasi benar untuk
mayoritas periode (Apr/May/Jun/Jul/Aug akun 611311 semuanya cocok persis
dengan Oracle) — dan MENAMBAHKAN indikator "ada N jurnal belum posting,
belum tercermin di angka ini" (lihat _query_unposted_budget_encumbrance)
supaya penggunanya tahu kapan harus mengecek langsung ke Oracle, alih-alih
diam-diam menampilkan angka yang belum tentu benar.

_query_reclass_gl (GL_JE_LINES kategori RECLASS/BUDGET, workaround data-entry
CKD Otto) tidak lagi dipakai di rumus manapun — Oracle sendiri tidak
menampilkan reclass di Funds Available Inquiry / Period Balances, jadi
memasukkannya justru bikin angka kita menyimpang dari Oracle. Method-nya
dibiarkan (tidak dihapus) untuk referensi/kebutuhan lain di masa depan.
"""
import asyncio
from app.database import get_oracle_connection
import structlog

logger = structlog.get_logger()

# ── Konfigurasi COA CKD Otto ──────────────────────────────────────────────────
DEPT_COL    = "segment3"                  # segment department di GL_CODE_COMBINATIONS
DEPT_VSET   = "CKDO_GL_COA_DEPARTMENT"   # value set untuk LOV department
ACCOUNT_COL = "segment4"                  # segment natural account
# ─────────────────────────────────────────────────────────────────────────────


class BudgetService:
    """Oracle EBS queries untuk Budget Monitoring — berlaku untuk semua department."""

    def _query(self, sql: str, params: dict = None) -> list[dict]:
        with get_oracle_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params or {})
            cols = [c[0].lower() for c in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]

    # ── LOV: Department ───────────────────────────────────────────────────────

    async def get_departments(self) -> dict:
        """
        Daftar department dari FND_FLEX_VALUES_VL (value set CKDO_GL_COA_DEPARTMENT).
        Dipakai sebagai dropdown di frontend.
        """
        sql = """
            SELECT
                ffv.flex_value   AS dept_code,
                ffvt.description AS dept_name
            FROM fnd_flex_values     ffv
            JOIN fnd_flex_values_tl  ffvt
                ON  ffvt.flex_value_id = ffv.flex_value_id
                AND ffvt.language      = USERENV('LANG')
            JOIN fnd_flex_value_sets ffvs
                ON  ffvs.flex_value_set_id = ffv.flex_value_set_id
            WHERE ffvs.flex_value_set_name = :vset
              AND ffv.enabled_flag         = 'Y'
              AND NVL(ffv.end_date_active, SYSDATE + 1) > SYSDATE
            ORDER BY ffv.flex_value
        """
        try:
            rows = await asyncio.to_thread(self._query, sql, {"vset": DEPT_VSET})
            return {"success": True, "data": rows}
        except Exception as e:
            logger.error("budget_dept_lov_error", error=str(e))
            return {"success": False, "error": str(e), "data": []}

    # ── Tahun yang tersedia ───────────────────────────────────────────────────

    async def get_available_years(self, dept: str) -> dict:
        """Tahun yang ada data budget untuk department tertentu di Oracle GL."""
        sql = f"""
            SELECT DISTINCT
                EXTRACT(YEAR FROM gp.start_date) AS budget_year
            FROM gl_balances gb
            JOIN gl_ledgers gl
                ON  gl.ledger_id            = gb.ledger_id
            JOIN gl_code_combinations gcc
                ON  gcc.code_combination_id = gb.code_combination_id
            JOIN gl_periods gp
                ON  gp.period_name          = gb.period_name
                AND gp.period_set_name      = gl.period_set_name
            WHERE gb.actual_flag    = 'B'
              AND  gcc.segment3 = :dept 
            ORDER BY budget_year DESC
        """
        try:
            rows = await asyncio.to_thread(self._query, sql, {"dept": dept})
            return {"success": True, "data": [int(r["budget_year"]) for r in rows]}
        except Exception as e:
            logger.error("budget_years_error", dept=dept, error=str(e))
            return {"success": False, "error": str(e), "data": []}

    # ── Ringkasan per akun ────────────────────────────────────────────────────

    async def get_summary(self, dept: str, year: int, month: int = None, account_code: str = None) -> dict:
        """
        Ringkasan budget vs realisasi per akun untuk satu department — layout
        & rumus sama dengan Oracle EBS "Funds Available Inquiry" (Amount Type
        "Year To Date Extended"):
        Budget      : GL_BALANCES (actual_flag='B')
        Encumbrance : GL_BALANCES (actual_flag='E')
        Actual      : GL_BALANCES (actual_flag='A')
        Funds Available : Budget − Encumbrance − Actual

        Tergantung parameter `month`:
        - `month` diisi  → Year-To-Date SAMPAI DENGAN bulan itu (mis. month=3
          → Januari-Maret dijumlah), sama seperti Oracle "Year To Date
          Extended". BUKAN Period-To-Date bulan itu saja.
        - `month` kosong (All Months) → total SATU TAHUN penuh (Jan-Des).
        `account_code` diisi → hanya akun itu; kosong → semua akun department.

        _query_budget/_query_actual_gl/_query_encumbrance_gl selalu GROUP BY
        per bulan, jadi baris per-bulan di-sum per akun di sini sebelum
        dijadikan daftar akun — kalau tidak, tiap bulan akan muncul sebagai
        "akun" terpisah.
        """
        budget_rows      = await asyncio.to_thread(self._query_budget, dept, year, month, account_code)
        actual_map       = await asyncio.to_thread(self._query_actual_summary, dept, year, month, account_code)
        encumbrance_map  = await asyncio.to_thread(self._query_encumbrance_summary, dept, year, month, account_code)
        unposted_rows    = await asyncio.to_thread(self._query_unposted_budget_encumbrance, dept, year, month, account_code)
        unposted_map: dict[str, dict] = {}
        for r in unposted_rows:
            code = str(r["account_code"])
            entry = unposted_map.setdefault(code, {"amount": 0, "lines": 0})
            entry["amount"] += int(r.get("unposted_amount") or 0)
            entry["lines"]  += int(r.get("line_count") or 0)

        # _query_budget always groups by (year, month, account) — it returns ONE
        # ROW PER MONTH per account, even when the WHERE clause lets several
        # months through (month=None for the whole year, or the YTD-cumulative
        # range below). Sum per account here first, or every month would show
        # up as its own duplicate "account" row with only that month's amount.
        budget_by_account: dict[str, dict] = {}
        for r in budget_rows:
            code = str(r["account_code"])
            name = str(r.get("account_name") or code)
            amt  = int(r.get("budget_amount") or 0)
            entry = budget_by_account.setdefault(code, {"account_name": name, "budget": 0})
            entry["budget"] += amt

        total_budget      = 0
        total_encumbrance = 0
        total_actual      = 0
        accounts          = []

        all_codes = set(budget_by_account) | set(actual_map) | set(encumbrance_map)
        for code in all_codes:
            info        = budget_by_account.get(code, {"account_name": code, "budget": 0})
            budget      = info["budget"]
            encumbrance = encumbrance_map.get(code, 0)
            actual      = actual_map.get(code, 0)
            funds_available = budget - encumbrance - actual
            total_budget      += budget
            total_encumbrance += encumbrance
            total_actual      += actual
            unposted = unposted_map.get(code, {"amount": 0, "lines": 0})
            accounts.append({
                "account_code":       code,
                "account_name":       info["account_name"],
                "budget":             budget,
                "encumbrance":        encumbrance,
                "actual":             actual,
                "funds_available":    funds_available,
                "unposted_pending":   unposted["amount"],
                "unposted_lines":     unposted["lines"],
            })

        accounts.sort(key=lambda a: a["account_code"])

        return {
            "dept":    dept,
            "year":    year,
            "month":   month,
            "account": account_code,
            "summary": {
                "total_budget":          total_budget,
                "total_encumbrance":     total_encumbrance,
                "total_actual":          total_actual,
                "total_funds_available": total_budget - total_encumbrance - total_actual,
                "total_unposted_lines":  sum(a["unposted_lines"] for a in accounts),
            },
            "accounts": accounts,
        }

    # ── Detail per akun per bulan ─────────────────────────────────────────────

    async def get_account_detail(self, dept: str, account_code: str, year: int, month: int = None) -> dict:
        """
        Rincian per periode untuk 1 akun — SAMA PERSIS dengan Oracle EBS
        "Period Balances (YTDE)" drilldown (per-period Budget/Encumbrance/
        Actual/Funds Available, bukan kertas kerja custom):
        - budget           dari GL_BALANCES (actual_flag='B'), PTD per bulan
        - encumbrance      dari GL_BALANCES (actual_flag='E'), PTD per bulan
        - actual           dari GL_BALANCES (actual_flag='A'), PTD per bulan —
          SAMA dengan yang dipakai get_summary, mencakup SEMUA sumber posting
          (AP Invoice, payroll, jurnal manual, dll). Versi sebelumnya salah
          pakai total klaim Expense Report saja di sini, yang cuma subset dari
          actual GL sesungguhnya — itu sebabnya angkanya tidak cocok dengan
          Oracle "Period Balances" (Expense Report tidak mencakup AP Invoice/
          payroll/jurnal lain yang juga membentuk actual_flag='A').
        - funds_available  = budget − encumbrance − actual (persis rumus
          Oracle, dihitung per periode — bukan budget − encumbrance saja)
        - `month` (opsional) = tampilkan periode Januari s.d. bulan itu saja,
          bukan satu tahun penuh — cocok dengan filter "sampai dengan" di
          get_summary, supaya rincian yang dibuka tidak melebihi filter Actual
          yang sedang dilihat user.

        Expense Report + Purchase Requisition tetap disertakan per periode
        sebagai `items` (transaksi pendukung, ditandai `source`) untuk
        transparansi apa yang membentuk Actual — TAPI jumlahnya TIDAK selalu
        sama dengan `actual` (GL actual mencakup AP Invoice/payroll juga,
        Expense Report+PR cuma sebagian sumbernya).
        """
        budget_rows = await asyncio.to_thread(
            self._query_budget, dept, year, month=None, account_code=account_code
        )
        budget_map = {int(r["month"]): int(r.get("budget_amount") or 0)
                      for r in budget_rows}

        encumbrance_rows = await asyncio.to_thread(
            self._query_encumbrance_gl, dept, year, month=None, account_code=account_code
        )
        encumbrance_map = {int(r["month"]): int(r.get("encumbrance_amount") or 0)
                            for r in encumbrance_rows}

        actual_rows = await asyncio.to_thread(
            self._query_actual_gl, dept, year, month=None, account_code=account_code
        )
        actual_map = {int(r["month"]): int(r.get("actual_amount") or 0) for r in actual_rows}

        unposted_rows = await asyncio.to_thread(
            self._query_unposted_budget_encumbrance, dept, year, month=None, account_code=account_code
        )
        unposted_map: dict[int, dict] = {}
        for r in unposted_rows:
            m = int(r["month"])
            entry = unposted_map.setdefault(m, {"amount": 0, "lines": 0})
            entry["amount"] += int(r.get("unposted_amount") or 0)
            entry["lines"]  += int(r.get("line_count") or 0)

        expense_items = await asyncio.to_thread(
            self._query_expense_report_items, dept, year, month=None, account_code=account_code
        )
        pr_items = await asyncio.to_thread(
            self._query_purchase_requisition_items, dept, year, month=None, account_code=account_code
        )

        items_by_month: dict[int, list] = {}
        for item in expense_items:
            m = int(item["month"])
            items_by_month.setdefault(m, []).append({**item, "source": "Expense Report"})
        for item in pr_items:
            m = int(item["month"])
            items_by_month.setdefault(m, []).append({**item, "source": "Purchase Requisition"})

        MONTH_NAMES = ["Jan","Feb","Mar","Apr","Mei","Jun",
                       "Jul","Agu","Sep","Okt","Nov","Des"]

        last_month = month if month else 12
        monthly = []
        for m in range(1, last_month + 1):
            budget          = budget_map.get(m, 0)
            encumbrance     = encumbrance_map.get(m, 0)
            actual          = actual_map.get(m, 0)
            funds_available = budget - encumbrance - actual
            month_items     = sorted(items_by_month.get(m, []), key=lambda i: i.get("expense_date") or "")
            unposted        = unposted_map.get(m, {"amount": 0, "lines": 0})
            monthly.append({
                "month":            m,
                "month_name":       MONTH_NAMES[m - 1],
                "budget":           budget,
                "encumbrance":      encumbrance,
                "actual":           actual,
                "funds_available":  funds_available,
                "unposted_pending": unposted["amount"],
                "unposted_lines":   unposted["lines"],
                "items": [
                    {
                        "description": i.get("description") or "",
                        "amount":      int(i.get("amount") or 0),
                        "date":        i.get("expense_date"),
                        "report_num":  i.get("report_num"),
                        "source":      i["source"],
                    }
                    for i in month_items
                ],
            })

        totals = {
            "budget":          sum(mm["budget"] for mm in monthly),
            "encumbrance":     sum(mm["encumbrance"] for mm in monthly),
            "actual":          sum(mm["actual"] for mm in monthly),
            "funds_available": sum(mm["funds_available"] for mm in monthly),
        }

        return {"dept": dept, "account_code": account_code, "year": year, "month": month,
                "monthly": monthly, "totals": totals}

    # ── Private: Budget dari GL ───────────────────────────────────────────────

    def _query_budget(self, dept: str, year: int,
                      month: int = None, account_code: str = None) -> list[dict]:
        sql = f"""
            SELECT
                EXTRACT(YEAR  FROM gp.start_date)              AS year,
                EXTRACT(MONTH FROM gp.start_date)              AS month,
                gcc.{ACCOUNT_COL}                              AS account_code,
                (SELECT ffvv.description
                 FROM   fnd_flex_values_vl  ffvv
                 JOIN   fnd_flex_value_sets ffvs
                        ON  ffvs.flex_value_set_id = ffvv.flex_value_set_id
                 JOIN   fnd_id_flex_segments fifs
                        ON  fifs.flex_value_set_id        = ffvs.flex_value_set_id
                 WHERE  fifs.application_id               = 101
                   AND  fifs.id_flex_code                 = 'GL#'
                   AND  fifs.application_column_name      = '{ACCOUNT_COL.upper()}'
                   AND  ffvv.flex_value                   = gcc.{ACCOUNT_COL}
                   AND  ROWNUM                            = 1) AS account_name,
                SUM(NVL(gb.period_net_dr, 0) - NVL(gb.period_net_cr, 0)) AS budget_amount
            FROM gl_balances gb
            JOIN gl_ledgers gl
                ON  gl.ledger_id            = gb.ledger_id
            JOIN gl_code_combinations gcc
                ON  gcc.code_combination_id = gb.code_combination_id
            JOIN gl_periods gp
                ON  gp.period_name          = gb.period_name
                AND gp.period_set_name      = gl.period_set_name
            WHERE gb.actual_flag            = 'B'
              AND gb.currency_code          = gl.currency_code
              AND  gcc.segment3 = :dept
              AND EXTRACT(YEAR FROM gp.start_date)  = :year
              AND (:month   IS NULL OR EXTRACT(MONTH FROM gp.start_date) <= :month)
              AND (:account IS NULL OR gcc.{ACCOUNT_COL} = :account)
            GROUP BY
                EXTRACT(YEAR  FROM gp.start_date),
                EXTRACT(MONTH FROM gp.start_date),
                gcc.{ACCOUNT_COL}
            ORDER BY month, account_code
        """
        return self._query(sql, {
            "dept": dept, "year": year,
            "month": month, "account": account_code,
        })

    # ── Private: Actual summary (per akun) dari GL_BALANCES ───────────────────
    # Sama persis dengan Oracle "Funds Available Inquiry" — actual_flag='A'
    # mencakup SEMUA sumber posting (AP Invoice, payroll, jurnal manual, dll),
    # bukan hanya AP Invoice seperti versi sebelumnya.

    def _query_actual_summary(self, dept: str, year: int,
                               month: int = None, account_code: str = None) -> dict[str, int]:
        rows = self._query_actual_gl(dept, year, month=month, account_code=account_code)
        totals: dict[str, int] = {}
        for r in rows:
            code = str(r["account_code"])
            totals[code] = totals.get(code, 0) + int(r.get("actual_amount") or 0)
        return totals

    # ── Private: Encumbrance summary (per akun) dari GL_BALANCES ──────────────

    def _query_encumbrance_summary(self, dept: str, year: int,
                                    month: int = None, account_code: str = None) -> dict[str, int]:
        rows = self._query_encumbrance_gl(dept, year, month=month, account_code=account_code)
        totals: dict[str, int] = {}
        for r in rows:
            code = str(r["account_code"])
            totals[code] = totals.get(code, 0) + int(r.get("encumbrance_amount") or 0)
        return totals

    # ── Private: Actual dari GL — per bulan, per akun ─────────────────────────

    def _query_actual_gl(self, dept: str, year: int,
                          month: int = None, account_code: str = None) -> list[dict]:
        sql = f"""
            SELECT
                EXTRACT(YEAR  FROM gp.start_date)              AS year,
                EXTRACT(MONTH FROM gp.start_date)              AS month,
                gcc.{ACCOUNT_COL}                              AS account_code,
                SUM(NVL(gb.period_net_dr, 0) - NVL(gb.period_net_cr, 0)) AS actual_amount
            FROM gl_balances gb
            JOIN gl_ledgers gl
                ON  gl.ledger_id            = gb.ledger_id
            JOIN gl_code_combinations gcc
                ON  gcc.code_combination_id = gb.code_combination_id
            JOIN gl_periods gp
                ON  gp.period_name          = gb.period_name
                AND gp.period_set_name      = gl.period_set_name
            WHERE gb.actual_flag            = 'A'
              AND gb.currency_code          = gl.currency_code
              AND  gcc.segment3 = :dept
              AND EXTRACT(YEAR FROM gp.start_date)  = :year
              AND (:month   IS NULL OR EXTRACT(MONTH FROM gp.start_date) <= :month)
              AND (:account IS NULL OR gcc.{ACCOUNT_COL} = :account)
            GROUP BY
                EXTRACT(YEAR  FROM gp.start_date),
                EXTRACT(MONTH FROM gp.start_date),
                gcc.{ACCOUNT_COL}
            ORDER BY month, account_code
        """
        return self._query(sql, {
            "dept": dept, "year": year,
            "month": month, "account": account_code,
        })

    # ── Private: Encumbrance dari GL — per bulan, per akun ────────────────────

    def _query_encumbrance_gl(self, dept: str, year: int,
                               month: int = None, account_code: str = None) -> list[dict]:
        sql = f"""
            SELECT
                EXTRACT(YEAR  FROM gp.start_date)              AS year,
                EXTRACT(MONTH FROM gp.start_date)              AS month,
                gcc.{ACCOUNT_COL}                              AS account_code,
                SUM(NVL(gb.period_net_dr, 0) - NVL(gb.period_net_cr, 0)) AS encumbrance_amount
            FROM gl_balances gb
            JOIN gl_ledgers gl
                ON  gl.ledger_id            = gb.ledger_id
            JOIN gl_code_combinations gcc
                ON  gcc.code_combination_id = gb.code_combination_id
            JOIN gl_periods gp
                ON  gp.period_name          = gb.period_name
                AND gp.period_set_name      = gl.period_set_name
            WHERE gb.actual_flag            = 'E'
              AND gb.currency_code          = gl.currency_code
              AND  gcc.segment3 = :dept
              AND EXTRACT(YEAR FROM gp.start_date)  = :year
              AND (:month   IS NULL OR EXTRACT(MONTH FROM gp.start_date) <= :month)
              AND (:account IS NULL OR gcc.{ACCOUNT_COL} = :account)
            GROUP BY
                EXTRACT(YEAR  FROM gp.start_date),
                EXTRACT(MONTH FROM gp.start_date),
                gcc.{ACCOUNT_COL}
            ORDER BY month, account_code
        """
        return self._query(sql, {
            "dept": dept, "year": year,
            "month": month, "account": account_code,
        })

    # ── Private: Jurnal Budget/Encumbrance yang BELUM di-post ─────────────────
    # GL_BALANCES cuma refleksi jurnal yang statusnya POSTED ('P') — kalau ada
    # jurnal budget/encumbrance yang masih 'U' (Unposted) di Oracle, dia TIDAK
    # ikut GL_BALANCES sampai benar-benar diposting, padahal layar Oracle
    # "Funds Available Inquiry" kadang sudah menghitungnya. Query ini CUMA
    # untuk mendeteksi & memberi tanda "ada N baris belum posting senilai Rp X
    # yang belum tercermin di atas" — sengaja TIDAK dipakai untuk mengoreksi
    # angka Budget/Encumbrance utama, karena draft unposted kadang adalah
    # duplikat basi yang sudah digantikan jurnal lain yang sudah posting
    # (ditemukan langsung di data CKD Otto — lihat catatan di docstring modul)
    # — menjumlahkannya begitu saja bisa salah, bukan cuma "kurang lengkap".

    def _query_unposted_budget_encumbrance(self, dept: str, year: int,
                                            month: int = None, account_code: str = None) -> list[dict]:
        sql = f"""
            SELECT
                EXTRACT(YEAR  FROM gp.start_date)              AS year,
                EXTRACT(MONTH FROM gp.start_date)              AS month,
                gcc.{ACCOUNT_COL}                              AS account_code,
                SUM(NVL(gjl.accounted_dr, 0) - NVL(gjl.accounted_cr, 0)) AS unposted_amount,
                COUNT(*)                                       AS line_count
            FROM gl_je_lines gjl
            JOIN gl_je_headers gjh
                ON  gjh.je_header_id        = gjl.je_header_id
            JOIN gl_ledgers gl
                ON  gl.ledger_id            = gjh.ledger_id
            JOIN gl_code_combinations gcc
                ON  gcc.code_combination_id = gjl.code_combination_id
            JOIN gl_periods gp
                ON  gp.period_name          = gjl.period_name
                AND gp.period_set_name      = gl.period_set_name
            WHERE gjh.actual_flag IN ('B', 'E')
              AND gjh.status              != 'P'
              AND  gcc.segment3 = :dept
              AND EXTRACT(YEAR FROM gp.start_date)  = :year
              AND (:month   IS NULL OR EXTRACT(MONTH FROM gp.start_date) <= :month)
              AND (:account IS NULL OR gcc.{ACCOUNT_COL} = :account)
            GROUP BY
                EXTRACT(YEAR  FROM gp.start_date),
                EXTRACT(MONTH FROM gp.start_date),
                gcc.{ACCOUNT_COL}
            ORDER BY month, account_code
        """
        return self._query(sql, {
            "dept": dept, "year": year,
            "month": month, "account": account_code,
        })

    # ── Private: Budget Reclass dari jurnal manual ────────────────────────────
    # Reclass seharusnya masuk lewat Budget Journal (langsung ke GL_BALANCES
    # actual_flag='B'), tapi di CKD Otto di-input sebagai jurnal ACTUAL biasa
    # dengan je_category 'RECLASS' atau 'BUDGET' (kesalahan prosedur import) —
    # sehingga harus di-query terpisah dan di-net-kan (debit − credit) di sini,
    # baru ditambahkan manual ke rumus Remain = Available + Reclass − Actual.

    def _query_reclass_gl(self, dept: str, year: int,
                           month: int = None, account_code: str = None) -> list[dict]:
        sql = f"""
            SELECT
                EXTRACT(YEAR  FROM gp.start_date)              AS year,
                EXTRACT(MONTH FROM gp.start_date)              AS month,
                gcc.{ACCOUNT_COL}                              AS account_code,
                SUM(NVL(gjl.entered_dr, 0) - NVL(gjl.entered_cr, 0)) AS reclass_amount,
                MAX(NVL(gjl.description, gjh.description))     AS note
            FROM gl_je_lines gjl
            JOIN gl_je_headers gjh
                ON  gjh.je_header_id        = gjl.je_header_id
                AND gjh.status              = 'P'
            JOIN gl_ledgers gl
                ON  gl.ledger_id            = gjh.ledger_id
            JOIN gl_code_combinations gcc
                ON  gcc.code_combination_id = gjl.code_combination_id
            JOIN gl_periods gp
                ON  gp.period_name          = gjl.period_name
                AND gp.period_set_name      = gl.period_set_name
            WHERE UPPER(gjh.je_category) IN ('RECLASS', 'BUDGET')
              AND  gcc.segment3 = :dept
              AND EXTRACT(YEAR FROM gp.start_date)  = :year
              AND (:month   IS NULL OR EXTRACT(MONTH FROM gp.start_date) <= :month)
              AND (:account IS NULL OR gcc.{ACCOUNT_COL} = :account)
            GROUP BY
                EXTRACT(YEAR  FROM gp.start_date),
                EXTRACT(MONTH FROM gp.start_date),
                gcc.{ACCOUNT_COL}
            ORDER BY month, account_code
        """
        return self._query(sql, {
            "dept": dept, "year": year,
            "month": month, "account": account_code,
        })

    # ── Private: Expense Report items (klaim HRGA — meal, petty cash, dll) ────

    def _query_expense_report_items(self, dept: str, year: int,
                                     month: int = None, account_code: str = None) -> list[dict]:
        sql = f"""
            SELECT
                EXTRACT(YEAR  FROM aerl.start_expense_date)          AS year,
                EXTRACT(MONTH FROM aerl.start_expense_date)          AS month,
                gcc.{ACCOUNT_COL}                              AS account_code,
                aerl.item_description                          AS description,
                aerl.amount,
                TO_CHAR(aerl.start_expense_date, 'YYYY-MM-DD')       AS expense_date,
                NVL(aerh.invoice_num, TO_CHAR(aerh.report_header_id)) AS report_num
            FROM ap_expense_report_lines aerl
            JOIN ap_expense_report_headers_v aerh
                ON  aerh.report_header_id    = aerl.report_header_id
            JOIN gl_code_combinations gcc
                ON  gcc.code_combination_id  = aerl.code_combination_id
            WHERE gcc.{DEPT_COL}             = :dept
              AND EXTRACT(YEAR  FROM aerl.start_expense_date) = :year
              AND (:month   IS NULL OR EXTRACT(MONTH FROM aerl.start_expense_date) = :month)
              AND (:account IS NULL OR gcc.{ACCOUNT_COL} = :account)
            ORDER BY aerl.start_expense_date, aerh.report_header_id, aerl.report_line_id
        """
        return self._query(sql, {
            "dept": dept, "year": year,
            "month": month, "account": account_code,
        })

    # ── Private: Purchase Requisition lines (belum di-invoice) ────────────────
    # NOTE: belum diverifikasi terhadap Oracle live — PO_REQ_DISTRIBUTIONS_ALL
    # adalah tabel standar EBS untuk distribusi akun GL sebuah baris PR, tapi
    # nama kolom persisnya (code_combination_id) belum dicek langsung di
    # instance CKD Otto. Kalau query ini error, laporkan pesan error Oracle-nya
    # supaya kolom/tabel bisa disesuaikan.

    def _query_purchase_requisition_items(self, dept: str, year: int,
                                           month: int = None, account_code: str = None) -> list[dict]:
        sql = f"""
            SELECT
                EXTRACT(YEAR  FROM prl.creation_date)          AS year,
                EXTRACT(MONTH FROM prl.creation_date)          AS month,
                gcc.{ACCOUNT_COL}                              AS account_code,
                prl.item_description                           AS description,
                NVL(prl.quantity, 0) * NVL(prl.unit_price, 0)  AS amount,
                TO_CHAR(prl.creation_date, 'YYYY-MM-DD')        AS expense_date,
                prh.segment1                                    AS report_num
            FROM po_requisition_lines_all prl
            JOIN po_requisition_headers_all prh
                ON  prh.requisition_header_id = prl.requisition_header_id
            JOIN po_req_distributions_all prd
                ON  prd.requisition_line_id   = prl.requisition_line_id
            JOIN gl_code_combinations gcc
                ON  gcc.code_combination_id   = prd.code_combination_id
            WHERE NVL(prl.cancel_flag, 'N')   = 'N'
              AND prh.authorization_status   NOT IN ('CANCELLED', 'REJECTED')
              AND gcc.{DEPT_COL}              = :dept
              AND EXTRACT(YEAR  FROM prl.creation_date) = :year
              AND (:month   IS NULL OR EXTRACT(MONTH FROM prl.creation_date) = :month)
              AND (:account IS NULL OR gcc.{ACCOUNT_COL} = :account)
            ORDER BY prl.creation_date, prh.requisition_header_id, prl.line_num
        """
        return self._query(sql, {
            "dept": dept, "year": year,
            "month": month, "account": account_code,
        })
