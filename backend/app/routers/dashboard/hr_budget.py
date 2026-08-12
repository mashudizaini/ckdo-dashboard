"""
Budget Monitoring Router
Route prefix : /api/v1/dashboard/hr/budget
Required role: hr_staff OR admin

Semua endpoint menerima parameter ?dept=<kode_dept>
sehingga modul ini bisa dipakai untuk semua department, tidak hanya HRGA.
"""
import io
from typing import Optional

import openpyxl
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.database import get_oracle_connection
from app.dependencies import require_role, CurrentUser, Roles
from app.services.budget_service import BudgetService, DEPT_COL, ACCOUNT_COL
import asyncio

router = APIRouter()
MONTH_NAMES = ["Jan","Feb","Mar","Apr","Mei","Jun","Jul","Agu","Sep","Okt","Nov","Des"]


# ── GET /debug — cek ketersediaan data di GL_BALANCES ────────────────────────

@router.get("/debug")
async def debug_gl_balance(
    dept: str          = Query(...),
    year: int          = Query(...),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    """
    Endpoint diagnostik — cek apa yang ada di GL_BALANCES untuk dept+year.
    Akses: /api/v1/dashboard/hr/budget/debug?dept=10&year=2026
    """
    def _run():
        with get_oracle_connection() as conn:
            cur = conn.cursor()

            # 1. Cek actual_flag yang tersedia
            cur.execute(f"""
                SELECT gb.actual_flag,
                       gb.currency_code,
                       COUNT(*)             AS row_count,
                       SUM(NVL(gb.period_net_dr,0) - NVL(gb.period_net_cr,0)) AS net_amount
                FROM   gl_balances gb
                JOIN   gl_ledgers gl  ON gl.ledger_id  = gb.ledger_id
                JOIN   gl_code_combinations gcc
                                      ON gcc.code_combination_id = gb.code_combination_id
                JOIN   gl_periods gp  ON gp.period_name     = gb.period_name
                                    AND gp.period_set_name  = gl.period_set_name
                WHERE  gcc.segment3 = :dept
                  AND  EXTRACT(YEAR FROM gp.start_date) = :year
                GROUP BY gb.actual_flag, gb.currency_code
                ORDER BY gb.actual_flag, gb.currency_code
            """, {"dept": dept, "year": year})
            cols = [c[0].lower() for c in cur.description]
            flags = [dict(zip(cols, row)) for row in cur.fetchall()]

            # 2. Cek 5 sample row dengan actual_flag = 'B'
            cur.execute(f"""
                SELECT gb.period_name,
                       gb.currency_code,
                       gb.actual_flag,
                       gb.budget_version_id,
                       gcc.{ACCOUNT_COL}  AS account_code,
                       gb.period_net_dr,
                       gb.period_net_cr
                FROM   gl_balances gb
                JOIN   gl_ledgers gl  ON gl.ledger_id  = gb.ledger_id
                JOIN   gl_code_combinations gcc
                                      ON gcc.code_combination_id = gb.code_combination_id
                JOIN   gl_periods gp  ON gp.period_name     = gb.period_name
                                    AND gp.period_set_name  = gl.period_set_name
                WHERE  gb.actual_flag  = 'B'
                  AND   gcc.segment3 = :dept
                  AND  EXTRACT(YEAR FROM gp.start_date) = :year
                  AND  ROWNUM <= 5
            """, {"dept": dept, "year": year})
            cols2 = [c[0].lower() for c in cur.description]
            samples = [dict(zip(cols2, row)) for row in cur.fetchall()]

            return {"flags": flags, "budget_samples": samples}

    try:
        result = await asyncio.to_thread(_run)
        return {
            "dept": dept, "year": year,
            "dept_col": DEPT_COL, "account_col": ACCOUNT_COL,
            **result,
            "hint": "Lihat 'flags' — jika actual_flag='B' tidak ada berarti budget belum diinput di Oracle GL untuk dept/tahun ini."
        }
    except Exception as e:
        return {"error": str(e)}


# ── GET /departments — LOV dropdown ──────────────────────────────────────────

@router.get("/departments")
async def get_departments(
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    """Daftar department dari Oracle (CKDO_GL_COA_DEPARTMENT value set)."""
    result = await BudgetService().get_departments()
    return result["data"] if result["success"] else []


# ── GET /years ────────────────────────────────────────────────────────────────

@router.get("/years")
async def get_available_years(
    dept: str          = Query(..., description="Kode department, contoh: HRGA"),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    """Daftar tahun yang ada data budget untuk department tertentu di Oracle GL."""
    result = await BudgetService().get_available_years(dept)
    return result["data"] if result["success"] else []


# ── GET /  — ringkasan per akun ───────────────────────────────────────────────

@router.get("")
async def get_budget_summary(
    dept:    str           = Query(...),
    year:    int           = Query(...),
    month:   Optional[int] = Query(None, description="Year-To-Date sampai bulan ini (mis. 3 = Jan-Mar); kosong = satu tahun penuh"),
    account: Optional[str] = Query(None, description="Kode akun (segment4) — kosong = semua akun department"),
    user:    CurrentUser   = Depends(require_role(Roles.HR)),
):
    """Ringkasan budget vs realisasi per akun untuk dept + tahun (opsional bulan YTD + akun)."""
    return await BudgetService().get_summary(dept, year, month, account)


# ── GET /account/{code} ───────────────────────────────────────────────────────

@router.get("/account/{account_code}")
async def get_account_detail(
    account_code: str,
    dept:  str           = Query(...),
    year:  int           = Query(...),
    month: Optional[int] = Query(None, description="Tampilkan periode Jan s.d. bulan ini saja — samakan dengan filter bulan di ringkasan"),
    user:  CurrentUser   = Depends(require_role(Roles.HR)),
):
    """Rincian per periode (Period Balances YTDE) untuk 1 akun dalam 1 department."""
    return await BudgetService().get_account_detail(dept, account_code, year, month)


# ── GET /export ───────────────────────────────────────────────────────────────

@router.get("/export")
async def export_budget(
    dept:    str           = Query(...),
    year:    int           = Query(...),
    month:   Optional[int] = Query(None),
    account: Optional[str] = Query(None),
    user:    CurrentUser   = Depends(require_role(Roles.HR)),
):
    """Export ringkasan Budget vs Realisasi ke Excel — layout sama dengan Oracle Funds Available Inquiry."""
    result = await BudgetService().get_summary(dept, year, month, account)
    accounts = result.get("accounts", [])
    summary  = result.get("summary", {})

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Budget {dept}"
    ws.append(["Department", "Tahun", "Filter Bulan (s.d.)", "Kode Akun", "Nama Akun",
               "Budget (Rp)", "Encumbrance (Rp)", "Actual (Rp)", "Funds Available (Rp)"])

    for acc in accounts:
        ws.append([
            dept, year,
            MONTH_NAMES[month - 1] if month else "Semua",
            acc["account_code"],
            acc["account_name"],
            acc["budget"],
            acc["encumbrance"],
            acc["actual"],
            acc["funds_available"],
        ])

    ws.append(["", "", "", "", "TOTAL",
               summary.get("total_budget", 0),
               summary.get("total_encumbrance", 0),
               summary.get("total_actual", 0),
               summary.get("total_funds_available", 0)])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"budget_{dept}_{year}" + (f"_{month:02d}" if month else "") + ".xlsx"

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )
