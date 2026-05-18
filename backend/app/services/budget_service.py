"""
Budget Monitoring Service
─────────────────────────────────────────
Query langsung ke Oracle EBS 12.2.8 — pola identik dengan ITService & PurchasingService.

COA Structure CKD Otto:
  segment3 = CKDO_GL_COA_DEPARTMENT  → department (parameter, tidak di-hardcode)
  segment4 = natural account           → kode akun

Dua sumber data:
  GL_BALANCES (actual_flag='B')        → anggaran per akun per periode
  AP_INVOICE_DISTRIBUTIONS_ALL         → realisasi AP Invoice per akun per periode

Rumus: Remain = Budget − Total Actual
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
            JOIN gl_code_combinations gcc
                ON  gcc.code_combination_id = gb.code_combination_id
            JOIN gl_periods gp
                ON  gp.period_name          = gb.period_name
                AND gp.period_set_name      = gb.period_set_name
            WHERE gb.actual_flag    = 'B'
              AND gcc.{DEPT_COL}    = :dept
              AND gp.period_type    = 'Month'
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
        Rincian per bulan untuk 1 akun:
        - budget dari GL_BALANCES
        - item AP Invoice dari AP_INVOICE_DISTRIBUTIONS_ALL
        """
        budget_rows = await asyncio.to_thread(
            self._query_budget, dept, year, month=None, account_code=account_code
        )
        budget_map = {int(r["month"]): int(r.get("budget_amount") or 0)
                      for r in budget_rows}

        items_all = await asyncio.to_thread(
            self._query_actual_items, dept, year, month=None, account_code=account_code
        )

        items_by_month: dict[int, list] = {}
        for item in items_all:
            m = int(item["month"])
            items_by_month.setdefault(m, []).append(item)

        MONTH_NAMES = ["Jan","Feb","Mar","Apr","Mei","Jun",
                       "Jul","Agu","Sep","Okt","Nov","Des"]

        all_months = sorted(set(list(budget_map.keys()) + list(items_by_month.keys())))
        monthly = []
        for m in all_months:
            budget       = budget_map.get(m, 0)
            month_items  = items_by_month.get(m, [])
            total_actual = sum(int(i.get("amount") or 0) for i in month_items)
            monthly.append({
                "month":        m,
                "month_name":   MONTH_NAMES[m - 1],
                "budget":       budget,
                "total_actual": total_actual,
                "remain":       budget - total_actual,
                "items": [
                    {
                        "description": i.get("description") or "",
                        "amount":      int(i.get("amount") or 0),
                        "date":        i.get("invoice_date"),
                        "invoice_num": i.get("invoice_num"),
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
                (SELECT ffvt.description
                 FROM   fnd_flex_values    ffv
                 JOIN   fnd_flex_values_tl ffvt
                        ON  ffvt.flex_value_id = ffv.flex_value_id
                        AND ffvt.language      = USERENV('LANG')
                 WHERE  ffv.flex_value        = gcc.{ACCOUNT_COL}
                   AND  ROWNUM               = 1)               AS account_name,
                SUM(gb.period_net_dr - gb.period_net_cr)       AS budget_amount
            FROM gl_balances gb
            JOIN gl_code_combinations gcc
                ON  gcc.code_combination_id = gb.code_combination_id
            JOIN gl_periods gp
                ON  gp.period_name          = gb.period_name
                AND gp.period_set_name      = gb.period_set_name
            WHERE gb.actual_flag            = 'B'
              AND gcc.{DEPT_COL}            = :dept
              AND gp.period_type            = 'Month'
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

    # ── Private: Actual summary (per akun) dari AP ────────────────────────────

    def _query_actual_summary(self, dept: str, year: int,
                               month: int = None) -> dict[str, int]:
        sql = f"""
            SELECT
                gcc.{ACCOUNT_COL}  AS account_code,
                SUM(aid.amount)    AS total_amount
            FROM ap_invoice_distributions_all aid
            JOIN ap_invoices_all ai
                ON  ai.invoice_id           = aid.invoice_id
            JOIN gl_code_combinations gcc
                ON  gcc.code_combination_id = aid.dist_code_combination_id
            WHERE ai.cancelled_date         IS NULL
              AND aid.reversal_flag         IS NULL
              AND gcc.{DEPT_COL}            = :dept
              AND EXTRACT(YEAR  FROM ai.invoice_date) = :year
              AND (:month IS NULL OR EXTRACT(MONTH FROM ai.invoice_date) = :month)
            GROUP BY gcc.{ACCOUNT_COL}
        """
        rows = self._query(sql, {"dept": dept, "year": year, "month": month})
        return {str(r["account_code"]): int(r.get("total_amount") or 0) for r in rows}

    # ── Private: AP Invoice items ─────────────────────────────────────────────

    def _query_actual_items(self, dept: str, year: int,
                             month: int = None, account_code: str = None) -> list[dict]:
        sql = f"""
            SELECT
                EXTRACT(YEAR  FROM ai.invoice_date)            AS year,
                EXTRACT(MONTH FROM ai.invoice_date)            AS month,
                gcc.{ACCOUNT_COL}                              AS account_code,
                NVL(ail.description, ai.description)
                    || CASE WHEN NVL(ail.description, ai.description) IS NOT NULL
                            THEN '' ELSE ' — ' || aps.vendor_name END AS description,
                aid.amount,
                TO_CHAR(ai.invoice_date, 'YYYY-MM-DD')         AS invoice_date,
                ai.invoice_num
            FROM ap_invoice_distributions_all aid
            JOIN ap_invoices_all ai
                ON  ai.invoice_id            = aid.invoice_id
            JOIN ap_invoice_lines_all ail
                ON  ail.invoice_id           = aid.invoice_id
                AND ail.line_number          = aid.invoice_line_number
            JOIN ap_suppliers aps
                ON  aps.vendor_id            = ai.vendor_id
            JOIN gl_code_combinations gcc
                ON  gcc.code_combination_id  = aid.dist_code_combination_id
            WHERE ai.cancelled_date          IS NULL
              AND aid.reversal_flag          IS NULL
              AND gcc.{DEPT_COL}             = :dept
              AND EXTRACT(YEAR  FROM ai.invoice_date) = :year
              AND (:month   IS NULL OR EXTRACT(MONTH FROM ai.invoice_date) = :month)
              AND (:account IS NULL OR gcc.{ACCOUNT_COL} = :account)
            ORDER BY ai.invoice_date, ai.invoice_id, aid.distribution_line_number
        """
        return self._query(sql, {
            "dept": dept, "year": year,
            "month": month, "account": account_code,
        })
