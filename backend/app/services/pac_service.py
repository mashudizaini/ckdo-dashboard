"""
PAC (Planning & Coordination) Service
─────────────────────────────────────────
Budget Usage Report — Actual vs Business Plan from Oracle EBS GL.
"""
import asyncio
from app.database import get_oracle_connection
import structlog

logger = structlog.get_logger()


class PACService:

    def _query(self, sql: str, params: dict = None) -> list[dict]:
        with get_oracle_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params or {})
            columns = [col[0].lower() for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    # ── Budget Usage Report ───────────────────────────────────────────────────

    async def get_budget_usage(self, filters: dict) -> dict:
        """
        Actual vs Budget (Business Plan) per Cost Center per Period.

        Oracle EBS tables used:
          GL_BALANCES          — actual & budget amounts per period
          GL_CODE_COMBINATIONS — account structure (company, dept, account, product)
          GL_LEDGERS           — ledger/set-of-books
          FND_FLEX_VALUES_VL   — segment value descriptions (cost center names, account names)
        """
        year      = int(filters.get("year") or 2026)
        month     = filters.get("month") or None          # 1-12, None = all months
        dept      = filters.get("cost_center") or None
        acct_type = filters.get("account_type") or None   # E=Expense, A=Asset, etc.
        ledger_id = filters.get("ledger_id") or None

        # Period name format in Oracle: "Jan-2026", "Feb-2026", ...
        # We filter by PERIOD_YEAR and optionally PERIOD_NUM
        sql = """
            SELECT
                gb.period_name                                              AS period_name,
                gb.period_year                                              AS period_year,
                gb.period_num                                               AS period_num,
                gcc.segment2                                                AS cost_center_code,
                NVL(cc_fv.description, gcc.segment2)                       AS cost_center_name,
                gcc.segment3                                                AS account_code,
                NVL(ac_fv.description, gcc.segment3)                       AS account_name,
                gcc.account_type                                            AS account_type,
                NVL(SUM(CASE WHEN gb.actual_flag = 'A'
                             THEN gb.period_net_dr - gb.period_net_cr
                             ELSE 0 END), 0)                               AS actual_amount,
                NVL(SUM(CASE WHEN gb.actual_flag = 'B'
                             THEN gb.period_net_dr - gb.period_net_cr
                             ELSE 0 END), 0)                               AS budget_amount,
                NVL(SUM(CASE WHEN gb.actual_flag = 'A'
                             THEN gb.begin_balance_dr - gb.begin_balance_cr
                             ELSE 0 END), 0)                               AS actual_ytd,
                NVL(SUM(CASE WHEN gb.actual_flag = 'B'
                             THEN gb.begin_balance_dr - gb.begin_balance_cr
                             ELSE 0 END), 0)                               AS budget_ytd
            FROM gl_balances gb
            JOIN gl_code_combinations gcc
                ON gcc.code_combination_id = gb.code_combination_id
            LEFT JOIN fnd_flex_values_vl cc_fv
                ON  cc_fv.flex_value      = gcc.segment2
                AND cc_fv.flex_value_set_id = (
                    SELECT flex_value_set_id FROM fnd_id_flex_segments
                    WHERE  application_id    = 101
                      AND  id_flex_code      = 'GL#'
                      AND  segment_name      = 'Cost Center'
                      AND  ROWNUM            = 1
                )
            LEFT JOIN fnd_flex_values_vl ac_fv
                ON  ac_fv.flex_value      = gcc.segment3
                AND ac_fv.flex_value_set_id = (
                    SELECT flex_value_set_id FROM fnd_id_flex_segments
                    WHERE  application_id    = 101
                      AND  id_flex_code      = 'GL#'
                      AND  segment_name      = 'Account'
                      AND  ROWNUM            = 1
                )
            WHERE gb.actual_flag           IN ('A', 'B')
              AND gb.period_year            = :p_year
              AND (:p_month    IS NULL OR gb.period_num      = :p_month)
              AND (:p_dept     IS NULL OR gcc.segment2        LIKE '%' || :p_dept || '%')
              AND (:p_acct_type IS NULL OR gcc.account_type   = :p_acct_type)
              AND (:p_ledger_id IS NULL OR gb.ledger_id       = :p_ledger_id)
              AND gcc.summary_flag          = 'N'
              AND NVL(gcc.enabled_flag, 'Y') = 'Y'
            GROUP BY
                gb.period_name, gb.period_year, gb.period_num,
                gcc.segment2, NVL(cc_fv.description, gcc.segment2),
                gcc.segment3, NVL(ac_fv.description, gcc.segment3),
                gcc.account_type
            ORDER BY gb.period_num, gcc.segment2, gcc.segment3
            FETCH FIRST 2000 ROWS ONLY
        """
        params = {
            "p_year":      year,
            "p_month":     int(month)    if month      else None,
            "p_dept":      dept,
            "p_acct_type": acct_type,
            "p_ledger_id": int(ledger_id) if ledger_id else None,
        }
        try:
            rows = await asyncio.to_thread(self._query, sql, params)

            # Server-side KPIs
            total_actual = sum(float(r.get("actual_amount") or 0) for r in rows)
            total_budget = sum(float(r.get("budget_amount") or 0) for r in rows)
            absorption   = round((total_actual / total_budget * 100), 2) if total_budget else 0

            # Monthly summary (for chart)
            monthly = {}
            for r in rows:
                k = (int(r["period_num"]), r["period_name"])
                if k not in monthly:
                    monthly[k] = {"period_num": k[0], "period_name": r["period_name"],
                                  "actual": 0.0, "budget": 0.0}
                monthly[k]["actual"] += float(r.get("actual_amount") or 0)
                monthly[k]["budget"] += float(r.get("budget_amount") or 0)
            monthly_list = sorted(monthly.values(), key=lambda x: x["period_num"])
            for m in monthly_list:
                m["actual"] = round(m["actual"], 0)
                m["budget"] = round(m["budget"], 0)
                m["absorption"] = round(m["actual"] / m["budget"] * 100, 1) if m["budget"] else 0

            return {
                "success": True,
                "count":   len(rows),
                "data":    rows,
                "monthly": monthly_list,
                "kpi": {
                    "total_actual":  round(total_actual, 0),
                    "total_budget":  round(total_budget, 0),
                    "absorption_pct": absorption,
                    "variance":      round(total_budget - total_actual, 0),
                },
            }
        except Exception as e:
            logger.error("budget_usage_error", error=str(e))
            return {"success": False, "error": str(e), "data": [], "monthly": [], "kpi": {}}

    async def get_ledgers(self) -> dict:
        """LOV: GL ledgers available."""
        sql = """
            SELECT ledger_id, name AS ledger_name, currency_code
            FROM gl_ledgers
            WHERE ledger_category_code = 'PRIMARY'
              AND object_type_code      = 'L'
            ORDER BY name
        """
        try:
            rows = await asyncio.to_thread(self._query, sql)
            return {"success": True, "data": rows}
        except Exception as e:
            return {"success": False, "error": str(e), "data": []}
