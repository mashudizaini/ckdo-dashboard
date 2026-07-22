from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.eis_database import get_eis_db as get_db
from app.dependencies import get_current_user

router = APIRouter()


@router.get("/pipeline")
async def pipeline_progress(
    year: int = Query(2025),
    db: AsyncSession = Depends(get_db), user = Depends(get_current_user),
):
    q = text("""
        SELECT pp.product_name, pp.supplier, pp.country_origin,
               per.period_num, per.period_name,
               ds.stage_name, ds.stage_order, ds.color_hex,
               fp.status_text
        FROM eis.fact_pipeline_progress fp
        JOIN eis.dim_pipeline_product pp ON fp.pipeline_product_id = pp.id
        JOIN eis.dim_period per ON fp.period_id = per.id
        JOIN eis.dim_dev_stage ds ON fp.stage_id = ds.id
        WHERE per.fiscal_year = :year
        ORDER BY pp.id, per.period_num
    """)
    result = await db.execute(q, {"year": year})
    rows = [dict(r) for r in result.mappings().all()]

    products = {}
    for r in rows:
        name = r["product_name"]
        if name not in products:
            products[name] = {
                "product_name": name,
                "supplier": r["supplier"],
                "country_origin": r["country_origin"],
                "months": {},
            }
        products[name]["months"][r["period_num"]] = {
            "stage_name": r["stage_name"],
            "stage_order": r["stage_order"],
            "color_hex": r["color_hex"],
            "status_text": r["status_text"],
        }
    return {"data": list(products.values())}


@router.get("/pipeline-summary")
async def pipeline_summary(
    year: int = Query(2025), period: int = Query(11),
    db: AsyncSession = Depends(get_db), user = Depends(get_current_user),
):
    q = text("""
        SELECT ds.stage_name, ds.stage_order, ds.color_hex, COUNT(*) as product_count
        FROM eis.fact_pipeline_progress fp
        JOIN eis.dim_dev_stage ds ON fp.stage_id = ds.id
        JOIN eis.dim_period per ON fp.period_id = per.id
        WHERE per.fiscal_year = :year AND per.period_num = :period
        GROUP BY ds.stage_name, ds.stage_order, ds.color_hex
        ORDER BY ds.stage_order
    """)
    result = await db.execute(q, {"year": year, "period": period})
    return {"data": [dict(r) for r in result.mappings().all()]}
