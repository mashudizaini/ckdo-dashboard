"""
Budget Monitoring Service
─────────────────────────────────────────
Query langsung ke Oracle EBS 12.2.8 — pola identik dengan ITService & PurchasingService.

COA Structure CKD Otto:
  segment3 = CKDO_GL_COA_DEPARTMENT  → department (parameter, tidak di-hardcode)
  segment4 = natural account           → kode akun

Sumber data:
  GL_BALANCES (actual_flag='B')            → budget per akun per periode
  GL_BALANCES (actual_flag='A')            → actual per akun per periode (ringkasan akun,
                                              cocok dengan Oracle Funds Available Inquiry)
  GL_BALANCES (actual_flag='E')            → encumbrance per akun per periode
  GL_JE_LINES/GL_JE_HEADERS (je_category   → budget reclass (di-net-kan debit−credit,
    IN ('RECLASS','BUDGET'))                 lihat catatan di _query_reclass_gl)
  AP_EXPENSE_REPORT_LINES +                → klaim expense report HRGA per bulan
  AP_EXPENSE_REPORT_HEADERS_V                (detail kertas kerja per akun, bukan AP Invoice)

Rumus (ringkasan akun):        Remain = Budget − Actual
Rumus (kertas kerja per bulan): Remain = Available + Reclass − Total Actual
                                 dengan Available = Budget − Encumbrance
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

    async def get_summary(self, dept: str, year: int, month: int = None) -> dict:
        """
        Ringkasan budget vs realisasi per akun untuk satu department.
        Budget  : GL_BALANCES (actual_flag='B')
        Actual  : AP_INVOICE_DISTRIBUTIONS_ALL
        Remain  : Budget − Actual
        """
        budget_rows = await asyncio.to_thread(self._query_budget, dept, year, month)
        actual_map  = await asyncio.to_thread(self._query_actual_summary, dept, year, month)

        total_budget = 0
        total_actual = 0
        accounts     = []

        for r in budget_rows:
            code   = str(r["account_code"])
            name   = str(r.get("account_name") or code)
            budget = int(r.get("budget_amount") or 0)
            actual = actual_map.get(code, 0)
            remain = budget - actual
            total_budget += budget
            total_actual += actual
            accounts.append({
                "account_code": code,
                "account_name": name,
                "budget": budget,
                "actual": actual,
                "remain": remain,
            })

        # Akun yang ada realisasi tapi belum ada di budget lines
        for code, actual in actual_map.items():
            if not any(a["account_code"] == code for a in accounts):
                total_actual += actual
                accounts.append({
                    "account_code": code,
                    "account_name": code,
                    "budget": 0,
                    "actual": actual,
                    "remain": -actual,
                })

        accounts.sort(key=lambda a: a["account_code"])

        return {
            "dept":  dept,
            "year":  year,
            "month": month,
            "summary": {
                "total_budget": total_budget,
                "total_actual": total_actual,
                "total_remain": total_budget - total_actual,
            },
            "accounts": accounts,
        }

    # ── Detail per akun per bulan ─────────────────────────────────────────────

    async def get_account_detail(self, dept: str, account_code: str, year: int) -> dict:
        """
        Rincian per bulan untuk 1 akun, format kertas kerja HRGA:
        - budget       dari GL_BALANCES (actual_flag='B')
        - encumbrance  dari GL_BALANCES (actual_flag='E')
        - available    = budget − encumbrance (belum dikurangi actual bulan ini —
          sama seperti "Funds Available" di Oracle Funds Available Inquiry)
        - reclass      dari GL_JE_LINES/GL_JE_HEADERS kategori 'RECLASS'/'BUDGET',
          di-net-kan (debit − credit) karena proses import reclass sebelumnya
          menghasilkan baris debit DAN credit untuk akun yang sama (kesalahan
          prosedur import, bukan reclass ganda)
        - items + total_actual dari AP_EXPENSE_REPORT_LINES + AP_EXPENSE_REPORT_HEADERS_V
          (klaim expense report HRGA — meal, petty cash, dll), BUKAN AP Invoice
        - remain       = available + reclass − total_actual
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

        reclass_rows = await asyncio.to_thread(
            self._query_reclass_gl, dept, year, month=None, account_code=account_code
        )
        reclass_map  = {int(r["month"]): int(r.get("reclass_amount") or 0) for r in reclass_rows}
        reclass_note = {int(r["month"]): (r.get("note") or "") for r in reclass_rows}

        items_all = await asyncio.to_thread(
            self._query_expense_report_items, dept, year, month=None, account_code=account_code
        )

        items_by_month: dict[int, list] = {}
        for item in items_all:
            m = int(item["month"])
            items_by_month.setdefault(m, []).append(item)

        MONTH_NAMES = ["Jan","Feb","Mar","Apr","Mei","Jun",
                       "Jul","Agu","Sep","Okt","Nov","Des"]

        all_months = sorted(set(
            list(budget_map.keys()) + list(encumbrance_map.keys())
            + list(reclass_map.keys()) + list(items_by_month.keys())
        ))
        monthly = []
        for m in all_months:
            budget       = budget_map.get(m, 0)
            encumbrance  = encumbrance_map.get(m, 0)
            available    = budget - encumbrance
            reclass      = reclass_map.get(m, 0)
            month_items  = items_by_month.get(m, [])
            total_actual = sum(int(i.get("amount") or 0) for i in month_items)
            remain       = available + reclass - total_actual
            monthly.append({
                "month":        m,
                "month_name":   MONTH_NAMES[m - 1],
                "budget":       budget,
                "encumbrance":  encumbrance,
                "available":    available,
                "reclass":      reclass,
                "note":         reclass_note.get(m, ""),
                "total_actual": total_actual,
                "remain":       remain,
                "items": [
                    {
                        "description": i.get("description") or "",
                        "amount":      int(i.get("amount") or 0),
                        "date":        i.get("expense_date"),
                        "report_num":  i.get("report_num"),
                    }
                    for i in month_items
                ],
            })

        return {"dept": dept, "account_code": account_code, "year": year, "monthly": monthly}

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
              AND (:month   IS NULL OR EXTRACT(MONTH FROM gp.start_date) = :month)
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
                               month: int = None) -> dict[str, int]:
        rows = self._query_actual_gl(dept, year, month=month)
        totals: dict[str, int] = {}
        for r in rows:
            code = str(r["account_code"])
            totals[code] = totals.get(code, 0) + int(r.get("actual_amount") or 0)
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
              AND (:month   IS NULL OR EXTRACT(MONTH FROM gp.start_date) = :month)
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
              AND (:month   IS NULL OR EXTRACT(MONTH FROM gp.start_date) = :month)
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
              AND (:month   IS NULL OR EXTRACT(MONTH FROM gp.start_date) = :month)
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
