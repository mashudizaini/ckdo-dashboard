"""
HR Budget Monitoring Router
Route prefix : /api/v1/dashboard/hr/budget
Required role: hr_staff OR admin

Excel template (2 sheets):
  Sheet "Budget"  — baris anggaran: Tahun|Bulan|Kode Akun|Nama Akun|Budget|Realisasi|Keterangan
  Sheet "Detail"  — rincian item: Tahun|Bulan|Kode Akun|Nama Item|Jumlah|Tanggal|Keterangan
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
    """Ringkasan budget vs realisasi per akun untuk tahun (dan opsional bulan) tertentu."""
    filters = [BudgetLine.year == year]
    if month:
        filters.append(BudgetLine.month == month)

    q = (
        select(
            BudgetLine.account_code,
            BudgetLine.account_name,
            func.sum(BudgetLine.budget_amount).label("budget"),
            func.sum(BudgetLine.actual_amount).label("actual"),
        )
        .where(*filters)
        .group_by(BudgetLine.account_code, BudgetLine.account_name)
        .order_by(BudgetLine.account_code)
    )

    result = await db.execute(q)
    rows = result.all()

    total_budget = 0
    total_actual = 0
    accounts = []

    for r in rows:
        budget = int(r.budget or 0)
        actual = int(r.actual or 0)
        variance = budget - actual
        pct = round(actual / budget * 100, 1) if budget else 0.0
        total_budget += budget
        total_actual += actual
        accounts.append({
            "account_code": r.account_code,
            "account_name": r.account_name,
            "budget": budget,
            "actual": actual,
            "variance": variance,
            "absorption_pct": pct,
        })

    total_variance = total_budget - total_actual
    total_pct = round(total_actual / total_budget * 100, 1) if total_budget else 0.0

    return {
        "year": year,
        "month": month,
        "summary": {
            "total_budget": total_budget,
            "total_actual": total_actual,
            "total_variance": total_variance,
            "absorption_pct": total_pct,
        },
        "accounts": accounts,
    }


# ── GET /years ────────────────────────────────────────────────────────────────

@router.get("/years")
async def get_available_years(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    """Daftar tahun yang sudah ada data budget-nya."""
    q = select(BudgetLine.year).distinct().order_by(BudgetLine.year.desc())
    result = await db.execute(q)
    return [r[0] for r in result.all()]


# ── GET /account/{code} — detail per akun ─────────────────────────────────────

@router.get("/account/{account_code}")
async def get_account_detail(
    account_code: str,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    """Rincian per bulan + item pengeluaran untuk satu akun dalam satu tahun."""
    q = (
        select(BudgetLine)
        .where(BudgetLine.year == year, BudgetLine.account_code == account_code)
        .order_by(BudgetLine.month)
    )
    result = await db.execute(q)
    lines = result.scalars().all()

    monthly = []
    for line in lines:
        budget = int(line.budget_amount or 0)
        actual = int(line.actual_amount or 0)

        qi = (
            select(BudgetItem)
            .where(
                BudgetItem.year == year,
                BudgetItem.month == line.month,
                BudgetItem.account_code == account_code,
            )
            .order_by(BudgetItem.item_date, BudgetItem.id)
        )
        ri = await db.execute(qi)
        items = ri.scalars().all()

        monthly.append({
            "month": line.month,
            "month_name": MONTH_NAMES[line.month - 1],
            "budget": budget,
            "actual": actual,
            "variance": budget - actual,
            "absorption_pct": round(actual / budget * 100, 1) if budget else 0.0,
            "items": [
                {
                    "name": i.item_name,
                    "amount": int(i.amount or 0),
                    "date": i.item_date.isoformat() if i.item_date else None,
                    "notes": i.notes,
                }
                for i in items
            ],
        })

    return {
        "account_code": account_code,
        "year": year,
        "monthly": monthly,
    }


# ── POST /upload — upload Excel ───────────────────────────────────────────────

@router.post("/upload")
async def upload_budget(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    """Upload file Excel budget. Sheet 'Budget' wajib, sheet 'Detail' opsional."""
    raw = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
    except Exception as e:
        raise HTTPException(400, f"File tidak valid: {e}")

    if "Budget" not in wb.sheetnames:
        raise HTTPException(400, "Sheet 'Budget' tidak ditemukan. Gunakan template yang tersedia.")

    batch_id = str(uuid.uuid4())[:8]
    upserted = 0
    items_added = 0
    years_seen: set[int] = set()

    # ── Sheet Budget ──────────────────────────────────────────────────────────
    ws = wb["Budget"]
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or row[0] is None:
            continue
        try:
            year = int(float(row[0]))
            month = int(float(row[1]))
            account_code = str(row[2]).strip()
            account_name = str(row[3]).strip()
        except (ValueError, TypeError, IndexError):
            continue
        if not (1 <= month <= 12) or not account_code:
            continue

        budget_amount = _to_int(row[4] if len(row) > 4 else 0)
        actual_amount = _to_int(row[5] if len(row) > 5 else 0)
        notes = str(row[6]).strip() if len(row) > 6 and row[6] else None

        stmt = pg_insert(BudgetLine).values(
            year=year,
            month=month,
            account_code=account_code,
            account_name=account_name,
            budget_amount=budget_amount,
            actual_amount=actual_amount,
            notes=notes,
            upload_batch_id=batch_id,
            uploaded_at=datetime.utcnow(),
        ).on_conflict_do_update(
            constraint="uq_budget_line",
            set_={
                "account_name": account_name,
                "budget_amount": budget_amount,
                "actual_amount": actual_amount,
                "notes": notes,
                "upload_batch_id": batch_id,
                "uploaded_at": datetime.utcnow(),
            },
        )
        await db.execute(stmt)
        upserted += 1
        years_seen.add(year)

    # ── Sheet Detail (opsional) ───────────────────────────────────────────────
    detail_sheet = next(
        (wb[n] for n in ["Detail", "Rincian", "Items"] if n in wb.sheetnames), None
    )
    if detail_sheet:
        # Hapus item lama untuk tahun yang diupload agar tidak duplikat
        if years_seen:
            await db.execute(
                delete(BudgetItem).where(
                    BudgetItem.year.in_(list(years_seen)),
                    BudgetItem.upload_batch_id != batch_id,
                )
            )

        for row in detail_sheet.iter_rows(min_row=2, values_only=True):
            if not row or row[0] is None:
                continue
            try:
                year = int(float(row[0]))
                month = int(float(row[1]))
                account_code = str(row[2]).strip()
                item_name = str(row[3]).strip() if row[3] else ""
            except (ValueError, TypeError, IndexError):
                continue
            if not (1 <= month <= 12) or not account_code or not item_name:
                continue

            amount = _to_int(row[4] if len(row) > 4 else 0)
            item_date_val = row[5] if len(row) > 5 else None
            from datetime import date as date_type
            item_date = (
                item_date_val.date()
                if hasattr(item_date_val, "date")
                else None
            )
            notes = str(row[6]).strip() if len(row) > 6 and row[6] else None

            db.add(BudgetItem(
                year=year,
                month=month,
                account_code=account_code,
                item_name=item_name,
                amount=amount,
                item_date=item_date,
                notes=notes,
                upload_batch_id=batch_id,
            ))
            items_added += 1

    db.add(BudgetUploadLog(
        batch_id=batch_id,
        filename=file.filename,
        year=min(years_seen) if years_seen else None,
        total_rows=upserted,
        upserted=upserted,
        items_added=items_added,
        uploaded_by=user.username,
        notes=f"years={sorted(years_seen)}",
    ))

    await db.commit()
    return {
        "batch_id": batch_id,
        "filename": file.filename,
        "upserted": upserted,
        "items_added": items_added,
        "years": sorted(years_seen),
    }


# ── GET /export — export ke Excel ─────────────────────────────────────────────

@router.get("/export")
async def export_budget(
    year: int = Query(...),
    month: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    """Export data budget ke file Excel."""
    filters = [BudgetLine.year == year]
    if month:
        filters.append(BudgetLine.month == month)

    q = (
        select(BudgetLine)
        .where(*filters)
        .order_by(BudgetLine.account_code, BudgetLine.month)
    )
    result = await db.execute(q)
    lines = result.scalars().all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Budget"
    ws.append(["Tahun", "Bulan", "Nama Bulan", "Kode Akun", "Nama Akun",
               "Budget (Rp)", "Realisasi (Rp)", "Selisih (Rp)", "% Serapan", "Keterangan"])

    for line in lines:
        budget = int(line.budget_amount or 0)
        actual = int(line.actual_amount or 0)
        variance = budget - actual
        pct = round(actual / budget * 100, 1) if budget else 0.0
        ws.append([
            line.year,
            line.month,
            MONTH_NAMES[line.month - 1],
            line.account_code,
            line.account_name,
            budget,
            actual,
            variance,
            pct,
            line.notes or "",
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    fname = f"budget_hrga_{year}"
    if month:
        fname += f"_{month:02d}"
    fname += ".xlsx"

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


# ── GET /template — download template Excel ───────────────────────────────────

@router.get("/template")
async def download_template(
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    """Download template Excel untuk upload budget HRGA."""
    wb = openpyxl.Workbook()

    # Sheet 1: Budget
    ws1 = wb.active
    ws1.title = "Budget"
    ws1.append(["Tahun", "Bulan", "Kode Akun", "Nama Akun", "Budget (Rp)", "Realisasi (Rp)", "Keterangan"])
    ws1.append([2026, 1, "5101", "Gaji Karyawan", 100_000_000, 95_000_000, ""])
    ws1.append([2026, 1, "5102", "ATK & Perlengkapan", 5_000_000, 3_500_000, ""])
    ws1.append([2026, 2, "5101", "Gaji Karyawan", 100_000_000, 98_000_000, ""])
    ws1.append([2026, 2, "5102", "ATK & Perlengkapan", 5_000_000, 4_200_000, ""])

    # Sheet 2: Detail
    ws2 = wb.create_sheet("Detail")
    ws2.append(["Tahun", "Bulan", "Kode Akun", "Nama Item", "Jumlah (Rp)", "Tanggal (YYYY-MM-DD)", "Keterangan"])
    ws2.append([2026, 1, "5102", "Kertas A4", 2_000_000, "2026-01-05", ""])
    ws2.append([2026, 1, "5102", "Lem Kertas", 500_000, "2026-01-05", ""])
    ws2.append([2026, 1, "5102", "Ballpoint", 200_000, "2026-01-10", ""])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=template_budget_hrga.xlsx"},
    )
