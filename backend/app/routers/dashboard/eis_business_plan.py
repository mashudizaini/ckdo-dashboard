from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.eis_database import get_eis_db as get_db
from app.dependencies import get_current_user
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class BusinessPlanEntry(BaseModel):
    fiscal_year: int
    plan_type: str
    category: str
    sub_category: Optional[str] = None
    jan: float = 0
    feb: float = 0
    mar: float = 0
    apr: float = 0
    may: float = 0
    jun: float = 0
    jul: float = 0
    aug: float = 0
    sep: float = 0
    oct: float = 0
    nov: float = 0
    dec_val: float = 0


@router.get("/list")
async def list_business_plans(
    year: int = Query(2025), plan_type: str = Query(None),
    db: AsyncSession = Depends(get_db), user = Depends(get_current_user),
):
    type_filter = "AND plan_type = :plan_type" if plan_type else ""
    q = text(f"""
        SELECT id, fiscal_year, plan_type, category, sub_category,
               jan, feb, mar, apr, may, jun, jul, aug, sep, oct, nov, "dec", total,
               created_by, created_at, updated_at
        FROM eis.business_plan
        WHERE fiscal_year = :year {type_filter}
        ORDER BY plan_type, category, sub_category
    """)
    params = {"year": year}
    if plan_type:
        params["plan_type"] = plan_type
    result = await db.execute(q, params)
    return {"data": [dict(r) for r in result.mappings().all()]}


@router.post("/save")
async def save_business_plan(
    entry: BusinessPlanEntry = Body(...),
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user),
):
    q = text("""
        INSERT INTO eis.business_plan
            (fiscal_year, plan_type, category, sub_category,
             jan, feb, mar, apr, may, jun, jul, aug, sep, oct, nov, "dec",
             created_by, updated_at)
        VALUES
            (:fiscal_year, :plan_type, :category, :sub_category,
             :jan, :feb, :mar, :apr, :may, :jun, :jul, :aug, :sep, :oct, :nov, :dec_val,
             :created_by, NOW())
        ON CONFLICT (fiscal_year, plan_type, category, sub_category)
        DO UPDATE SET
            jan = EXCLUDED.jan, feb = EXCLUDED.feb, mar = EXCLUDED.mar,
            apr = EXCLUDED.apr, may = EXCLUDED.may, jun = EXCLUDED.jun,
            jul = EXCLUDED.jul, aug = EXCLUDED.aug, sep = EXCLUDED.sep,
            oct = EXCLUDED.oct, nov = EXCLUDED.nov, "dec" = EXCLUDED."dec",
            updated_at = NOW()
        RETURNING id
    """)
    result = await db.execute(q, {
        **entry.model_dump(),
        "created_by": user.full_name or user.username,
    })
    await db.commit()
    row = result.fetchone()
    return {"message": "Saved", "id": row[0] if row else None}


@router.delete("/{bp_id}")
async def delete_business_plan(
    bp_id: int,
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user),
):
    await db.execute(text("DELETE FROM eis.business_plan WHERE id = :id"), {"id": bp_id})
    await db.commit()
    return {"message": "Deleted"}


@router.get("/types")
async def plan_types():
    return {"data": [
        "Sales", "COGS", "OPEX", "Production",
        "Employee", "Budget", "Cashflow", "Financial Target",
    ]}
