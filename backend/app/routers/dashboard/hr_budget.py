"""
HR Budget Monitoring Router
Route prefix : /api/v1/dashboard/hr/budget
Required role: hr_staff OR admin

Dua sumber data Oracle yang di-upload terpisah via Excel:
  Sheet "Budget"  — dari Oracle modul Budget:
    Tahun | Bulan | Kode Akun | Nama Akun | Budget | Available | Reclass | Ket Reclass

  Sheet "Actual"  — dari Oracle modul AP Invoice:
    Tahun | Bulan | Kode Akun | Deskripsi Transaksi | Jumlah | Tanggal Invoice

Rumus:
  Total Actual = SUM(items per bulan per akun)
  Remain       = Available + Reclass - Total Actual
"""
import io
import uuid
from datetime import datetime
from typing import Optional

import openpyxl
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role, CurrentUser, Roles
from app.models.budget import BudgetLine, BudgetItem, BudgetUploadLog

router = APIRouter()

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
               "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def _to_int(val) -> int:
    try:
        return int(float(val or 0))
    except (ValueError, TypeError):
        return 0


# ── GET /  — ringkasan per akun ───────────────────────────────────────────────

@router.get("")
async def get_budget_summary(
    year: int = Query(...),
    month: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    """
    Ringkasan per akun: budget, available, reclass, total actual (dari items), remain.
    """
    line_filters = [BudgetLine.year == year]
    item_filters = [BudgetItem.year == year]
    if month:
        line_filters.append(BudgetLine.month == month)
        item_filters.append(BudgetItem.month == month)

    # Total actual per akun dari item transaksi
    actual_q = (
        select(
            BudgetItem.account_code,
            func.sum(BudgetItem.amount).label("total_actual"),
        )
        .where(*item_filters)
        .group_by(BudgetItem.account_code)
    )
    actual_result = await db.execute(actual_q)
    actual_map = {r.account_code: int(r.total_actual or 0) for r in actual_result.all()}

    # Budget lines
    line_q = (
        select(
            BudgetLine.account_code,
            BudgetLine.account_name,
            func.sum(BudgetLine.budget_amount).label("budget"),
            func.sum(BudgetLine.available_amount).label("available"),
            func.sum(BudgetLine.reclass_amount).label("reclass"),
        )
        .where(*line_filters)
        .group_by(BudgetLine.account_code, BudgetLine.account_name)
        .order_by(BudgetLine.account_code)
    )
    line_result = await db.execute(line_q)
    rows = line_result.all()

    accounts = []
    total_budget = total_actual_all = total_available = total_reclass = 0

    for r in rows:
        budget    = int(r.budget    or 0)
        available = int(r.available or 0)
        reclass   = int(r.reclass   or 0)
        actual    = actual_map.get(r.account_code, 0)
        remain    = available + reclass - actual

        total_budget    += budget
        total_available += available
        total_reclass   += reclass
        total_actual_all += actual

        accounts.append({
            "account_code": r.account_code,
            "account_name": r.account_name,
            "budget":    budget,
            "available": available,
            "reclass":   reclass,
            "actual":    actual,
            "remain":    remain,
        })

    total_remain = total_available + total_reclass - total_actual_all

    return {
        "year": year,
        "month": month,
        "summary": {
            "total_budget":    total_budget,
            "total_available": total_available,
            "total_reclass":   total_reclass,
            "total_actual":    total_actual_all,
            "total_remain":    total_remain,
        },
        "accounts": accounts,
    }


# ── GET /years ────────────────────────────────────────────────────────────────

@router.get("/years")
async def get_available_years(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    q = select(BudgetLine.year).distinct().order_by(BudgetLine.year.desc())
    result = await db.execute(q)
    return [r[0] for r in result.all()]


# ── GET /account/{code} — detail per bulan ────────────────────────────────────

@router.get("/account/{account_code}")
async def get_account_detail(
    account_code: str,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    """
    Rincian per bulan untuk satu akun:
    - budget, available, reclass, reclass_note dari BudgetLine
    - item-item AP Invoice dari BudgetItem
    - total_actual = SUM(items), remain = available + reclass - total_actual
    """
    line_q = (
        select(BudgetLine)
        .where(BudgetLine.year == year, BudgetLine.account_code == account_code)
        .order_by(BudgetLine.month)
    )
    line_result = await db.execute(line_q)
    lines = line_result.scalars().all()

    monthly = []
    for line in lines:
        budget    = int(line.budget_amount    or 0)
        available = int(line.available_amount or 0)
        reclass   = int(line.reclass_amount   or 0)

        # Item transaksi AP Invoice bulan ini
        item_q = (
            select(BudgetItem)
            .where(
                BudgetItem.year == year,
                BudgetItem.month == line.month,
                BudgetItem.account_code == account_code,
            )
            .order_by(BudgetItem.invoice_date, BudgetItem.id)
        )
        item_result = await db.execute(item_q)
        items = item_result.scalars().all()

        total_actual = sum(int(i.amount or 0) for i in items)
        remain       = available + reclass - total_actual

        monthly.append({
            "month":        line.month,
            "month_name":   MONTH_NAMES[line.month - 1],
            "budget":       budget,
            "available":    available,
            "reclass":      reclass,
            "reclass_note": line.reclass_note,
            "total_actual": total_actual,
            "remain":       remain,
            "items": [
                {
                    "description": i.description,
                    "amount":      int(i.amount or 0),
                    "date":        i.invoice_date.isoformat() if i.invoice_date else None,
                    "notes":       i.notes,
                }
                for i in items
            ],
        })

    return {"account_code": account_code, "year": year, "monthly": monthly}


# ── POST /upload/budget — upload data Budget dari Oracle ─────────────────────

@router.post("/upload/budget")
async def upload_budget_data(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    """
    Upload data anggaran dari Oracle modul Budget.
    Sheet wajib: 'Budget'
    Kolom: Tahun | Bulan | Kode Akun | Nama Akun | Budget | Available | Reclass | Ket Reclass
    """
    raw = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
    except Exception as e:
        raise HTTPException(400, f"File tidak valid: {e}")

    if "Budget" not in wb.sheetnames:
        raise HTTPException(400, "Sheet 'Budget' tidak ditemukan. Gunakan template.")

    batch_id = str(uuid.uuid4())[:8]
    upserted = 0

    for row in wb["Budget"].iter_rows(min_row=2, values_only=True):
        if not row or row[0] is None:
            continue
        try:
            year         = int(float(row[0]))
            month        = int(float(row[1]))
            account_code = str(row[2]).strip()
            account_name = str(row[3]).strip()
        except (ValueError, TypeError, IndexError):
            continue
        if not (1 <= month <= 12) or not account_code:
            continue

        budget_amount    = _to_int(row[4] if len(row) > 4 else 0)
        available_amount = _to_int(row[5] if len(row) > 5 else 0)
        reclass_amount   = _to_int(row[6] if len(row) > 6 else 0)
        reclass_note     = str(row[7]).strip() if len(row) > 7 and row[7] else None

        stmt = pg_insert(BudgetLine).values(
            year=year, month=month,
            account_code=account_code, account_name=account_name,
            budget_amount=budget_amount,
            available_amount=available_amount,
            reclass_amount=reclass_amount,
            reclass_note=reclass_note,
            upload_batch_id=batch_id,
            uploaded_at=datetime.utcnow(),
        ).on_conflict_do_update(
            constraint="uq_budget_line",
            set_={
                "account_name":     account_name,
                "budget_amount":    budget_amount,
                "available_amount": available_amount,
                "reclass_amount":   reclass_amount,
                "reclass_note":     reclass_note,
                "upload_batch_id":  batch_id,
                "uploaded_at":      datetime.utcnow(),
            },
        )
        await db.execute(stmt)
        upserted += 1

    db.add(BudgetUploadLog(
        batch_id=batch_id, filename=file.filename, sheet_type="Budget",
        total_rows=upserted, upserted=upserted, uploaded_by=user.username,
    ))
    await db.commit()
    return {"batch_id": batch_id, "upserted": upserted}


# ── POST /upload/actual — upload data Realisasi dari Oracle AP Invoice ────────

@router.post("/upload/actual")
async def upload_actual_data(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    """
    Upload data realisasi dari Oracle modul AP Invoice.
    Sheet wajib: 'Actual'
    Kolom: Tahun | Bulan | Kode Akun | Deskripsi | Jumlah | Tanggal Invoice
    """
    raw = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
    except Exception as e:
        raise HTTPException(400, f"File tidak valid: {e}")

    if "Actual" not in wb.sheetnames:
        raise HTTPException(400, "Sheet 'Actual' tidak ditemukan. Gunakan template.")

    batch_id  = str(uuid.uuid4())[:8]
    inserted  = 0
    years_months: set[tuple] = set()

    for row in wb["Actual"].iter_rows(min_row=2, values_only=True):
        if not row or row[0] is None:
            continue
        try:
            year         = int(float(row[0]))
            month        = int(float(row[1]))
            account_code = str(row[2]).strip()
            description  = str(row[3]).strip() if row[3] else ""
        except (ValueError, TypeError, IndexError):
            continue
        if not (1 <= month <= 12) or not account_code or not description:
            continue

        amount = _to_int(row[4] if len(row) > 4 else 0)
        date_val = row[5] if len(row) > 5 else None
        from datetime import date as date_type
        invoice_date = date_val.date() if hasattr(date_val, "date") else None
        notes = str(row[6]).strip() if len(row) > 6 and row[6] else None

        db.add(BudgetItem(
            year=year, month=month, account_code=account_code,
            description=description, amount=amount,
            invoice_date=invoice_date, notes=notes,
            upload_batch_id=batch_id, uploaded_at=datetime.utcnow(),
        ))
        inserted += 1
        years_months.add((year, month, account_code))

    db.add(BudgetUploadLog(
        batch_id=batch_id, filename=file.filename, sheet_type="Actual",
        total_rows=inserted, upserted=inserted, uploaded_by=user.username,
        notes=f"combos={len(years_months)}",
    ))
    await db.commit()
    return {"batch_id": batch_id, "inserted": inserted}


# ── GET /export ───────────────────────────────────────────────────────────────

@router.get("/export")
async def export_budget(
    year: int = Query(...),
    month: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    """Export ringkasan Budget vs Realisasi ke Excel."""
    line_filters = [BudgetLine.year == year]
    item_filters = [BudgetItem.year == year]
    if month:
        line_filters.append(BudgetLine.month == month)
        item_filters.append(BudgetItem.month == month)

    actual_q = (
        select(BudgetItem.account_code, BudgetItem.month,
               func.sum(BudgetItem.amount).label("total_actual"))
        .where(*item_filters)
        .group_by(BudgetItem.account_code, BudgetItem.month)
    )
    actual_res = await db.execute(actual_q)
    actual_map = {(r.account_code, r.month): int(r.total_actual or 0)
                  for r in actual_res.all()}

    q = (select(BudgetLine)
         .where(*line_filters)
         .order_by(BudgetLine.account_code, BudgetLine.month))
    lines = (await db.execute(q)).scalars().all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Budget Monitoring"
    ws.append(["Tahun", "Bulan", "Kode Akun", "Nama Akun",
               "Budget (Rp)", "Available (Rp)", "Reclass (Rp)",
               "Total Actual (Rp)", "Remain (Rp)", "Ket Reclass"])

    for line in lines:
        budget    = int(line.budget_amount    or 0)
        available = int(line.available_amount or 0)
        reclass   = int(line.reclass_amount   or 0)
        actual    = actual_map.get((line.account_code, line.month), 0)
        remain    = available + reclass - actual
        ws.append([
            line.year, line.month, line.account_code, line.account_name,
            budget, available, reclass, actual, remain,
            line.reclass_note or "",
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"budget_hrga_{year}" + (f"_{month:02d}" if month else "") + ".xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


# ── GET /template ─────────────────────────────────────────────────────────────

@router.get("/template")
async def download_template(
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    """Download template Excel (2 file terpisah dijadikan 2 sheet)."""
    wb = openpyxl.Workbook()

    # Sheet 1: Budget (dari Oracle modul Budget)
    ws1 = wb.active
    ws1.title = "Budget"
    ws1.append(["Tahun", "Bulan", "Kode Akun", "Nama Akun",
                "Budget (Rp)", "Available (Rp)", "Reclass (Rp)", "Ket Reclass"])
    ws1.append([2026, 1, "5102", "Spec meal & Entertainment", 19_000_000, 13_300_000, 12_000_000,
                "Budget reclass from Oct - Dec to Jan 2026"])
    ws1.append([2026, 2, "5102", "Spec meal & Entertainment", 19_000_000, 19_000_000, 0, ""])

    # Sheet 2: Actual (dari Oracle modul AP Invoice)
    ws2 = wb.create_sheet("Actual")
    ws2.append(["Tahun", "Bulan", "Kode Akun", "Deskripsi Transaksi",
                "Jumlah (Rp)", "Tanggal Invoice (YYYY-MM-DD)", "Keterangan"])
    ws2.append([2026, 1, "5102", "Spec meal Jan 2026",          3_312_030, "2026-01-15", ""])
    ws2.append([2026, 1, "5102", "Claim meeting HRGA Dec 25",   2_397_209, "2026-01-20", ""])
    ws2.append([2026, 1, "5102", "Petty cash renew Q1",           700_000, "2026-01-05", ""])
    ws2.append([2026, 1, "5102", "Spec meal Q1",               4_600_000, "2026-01-10", ""])
    ws2.append([2026, 1, "5102", "Birthday Cake",             14_000_000, "2026-01-25", ""])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=template_budget_hrga.xlsx"},
    )
