"""
Budget Monitoring Router
Route prefix : /api/v1/dashboard/general/budget
Required role: any authenticated user

Moved here from HRGA (was /dashboard/hr/budget) — this module has always
accepted an arbitrary ?dept=<kode_dept>, so it was never really an HRGA-only
concern (see budget_service.py's own docstring). Access is now controlled
per-user instead of per-role: each caller can only query their own team's
department code (resolved via budget_access_service.resolve_budget_access,
which matches their login to an Employee row and looks up that team's
Oracle dept_code) — except the IT team and a short list of exempted users
(see EXEMPT_USERNAMES in budget_access_service.py), who can query any dept.

  GET /my-access   — the caller's own access: {allowed_all, dept_code, dept_name}
  GET /departments — full LOV (unrestricted — just codes/names, not financial data)
  GET /years       — restricted to the caller's own dept unless allowed_all
  GET ""           — restricted (budget summary)
  GET /account/{code} — restricted (account drill-down)
  GET /export      — restricted (Excel export)
  GET /debug       — restricted (diagnostic query)
"""
import io
from typing import Optional

import openpyxl
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_oracle_connection, get_db
from app.dependencies import get_current_user, CurrentUser
from app.services.budget_service import BudgetService, DEPT_COL, ACCOUNT_COL
from app.services.budget_access_service import resolve_budget_access
import asyncio

router = APIRouter()
MONTH_NAMES = ["Jan","Feb","Mar","Apr","Mei","Jun","Jul","Agu","Sep","Okt","Nov","Des"]


async def _enforce_dept_access(user: CurrentUser, dept: str, db: AsyncSession) -> None:
    access = await resolve_budget_access(user, db)
    if access["allowed_all"]:
        return
    if not access["dept_code"] or dept != access["dept_code"]:
        raise HTTPException(403, "You can only view budget for your own team.")


# ── GET /my-access — the caller's own team/permission, for the frontend's
#    Team selector (disabled + defaulted unless allowed_all) ────────────────

@router.get("/my-access")
async def get_my_access(
    user: CurrentUser = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    return await resolve_budget_access(user, db)


# ── GET /debug — cek ketersediaan data di GL_BALANCES ────────────────────────

@router.get("/debug")
async def debug_gl_balance(
    dept: str          = Query(...),
    year: int          = Query(...),
    user: CurrentUser  = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    """
    Endpoint diagnostik — cek apa yang ada di GL_BALANCES untuk dept+year.
    Akses: /api/v1/dashboard/general/budget/debug?dept=10&year=2026
    """
    await _enforce_dept_access(user, dept, db)

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
    user: CurrentUser = Depends(get_current_user),
):
    """Daftar department dari Oracle (CKDO_GL_COA_DEPARTMENT value set) —
    unrestricted (codes/names only, no financial data) so a restricted
    user's Team selector can still show their own department's name."""
    result = await BudgetService().get_departments()
    return result["data"] if result["success"] else []


# ── GET /years ────────────────────────────────────────────────────────────────

@router.get("/years")
async def get_available_years(
    dept: str          = Query(..., description="Kode department, contoh: HRGA"),
    user: CurrentUser  = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    """Daftar tahun yang ada data budget untuk department tertentu di Oracle GL."""
    await _enforce_dept_access(user, dept, db)
    result = await BudgetService().get_available_years(dept)
    return result["data"] if result["success"] else []


# ── GET /  — ringkasan per akun ───────────────────────────────────────────────

@router.get("")
async def get_budget_summary(
    dept:    str           = Query(...),
    year:    int           = Query(...),
    month:   Optional[int] = Query(None, description="Year-To-Date sampai bulan ini (mis. 3 = Jan-Mar); kosong = satu tahun penuh"),
    account: Optional[str] = Query(None, description="Kode akun (segment4) — kosong = semua akun department"),
    user:    CurrentUser   = Depends(get_current_user),
    db:      AsyncSession  = Depends(get_db),
):
    """Ringkasan budget vs realisasi per akun untuk dept + tahun (opsional bulan YTD + akun)."""
    await _enforce_dept_access(user, dept, db)
    return await BudgetService().get_summary(dept, year, month, account)


# ── GET /account/{code} ───────────────────────────────────────────────────────

@router.get("/account/{account_code}")
async def get_account_detail(
    account_code: str,
    dept:  str           = Query(...),
    year:  int           = Query(...),
    month: Optional[int] = Query(None, description="Tampilkan periode Jan s.d. bulan ini saja — samakan dengan filter bulan di ringkasan"),
    user:  CurrentUser   = Depends(get_current_user),
    db:    AsyncSession  = Depends(get_db),
):
    """Rincian per periode (Period Balances YTDE) untuk 1 akun dalam 1 department."""
    await _enforce_dept_access(user, dept, db)
    return await BudgetService().get_account_detail(dept, account_code, year, month)


# ── GET /export ───────────────────────────────────────────────────────────────

@router.get("/export")
async def export_budget(
    dept:    str           = Query(...),
    year:    int           = Query(...),
    month:   Optional[int] = Query(None),
    account: Optional[str] = Query(None),
    user:    CurrentUser   = Depends(get_current_user),
    db:      AsyncSession  = Depends(get_db),
):
    """Export ringkasan Budget vs Realisasi ke Excel — layout sama dengan Oracle Funds Available Inquiry."""
    await _enforce_dept_access(user, dept, db)
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
