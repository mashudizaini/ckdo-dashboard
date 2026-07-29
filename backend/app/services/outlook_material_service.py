"""
Outlook Material Service — PAC module.
Stores and retrieves the reference source files (economic reports, market
data, etc.) uploaded ahead of writing the Business Plan Outlook.
"""
import os
from datetime import datetime
from typing import Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.outlook_material import OutlookMaterial
import structlog

logger = structlog.get_logger()

_UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", "outlook_materials"
)
os.makedirs(_UPLOAD_DIR, exist_ok=True)


class OutlookMaterialService:

    def storage_path(self, filename: str) -> str:
        return os.path.join(_UPLOAD_DIR, filename)

    async def save_files(
        self,
        db: AsyncSession,
        plan_year: int,
        files: list,
        username: str,
    ) -> dict:
        saved = []
        for file in files:
            content = await file.read()
            ext = os.path.splitext(file.filename or "")[1]
            stored_name = f"{plan_year}_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}{ext}"
            with open(self.storage_path(stored_name), "wb") as f:
                f.write(content)

            row = OutlookMaterial(
                plan_year=plan_year,
                filename=stored_name,
                original_name=file.filename or stored_name,
                content_type=file.content_type,
                file_size=len(content),
                uploaded_by=username,
            )
            db.add(row)
            await db.flush()
            await db.refresh(row)
            saved.append(self._to_dict(row))
        return {"success": True, "count": len(saved), "data": saved}

    async def list_materials(self, db: AsyncSession, plan_year: Optional[int] = None) -> dict:
        q = select(OutlookMaterial).order_by(OutlookMaterial.created_at.desc())
        if plan_year:
            q = q.where(OutlookMaterial.plan_year == plan_year)
        result = await db.execute(q)
        rows = result.scalars().all()
        return {"success": True, "count": len(rows), "data": [self._to_dict(r) for r in rows]}

    async def get_material(self, db: AsyncSession, material_id: int) -> Optional[OutlookMaterial]:
        return await db.get(OutlookMaterial, material_id)

    async def delete_material(self, db: AsyncSession, material_id: int) -> dict:
        row = await db.get(OutlookMaterial, material_id)
        if not row:
            return {"success": False, "error": "Not found"}
        path = self.storage_path(row.filename)
        if os.path.exists(path):
            os.remove(path)
        await db.execute(delete(OutlookMaterial).where(OutlookMaterial.id == material_id))
        return {"success": True, "message": f"Deleted material #{material_id}"}

    def _to_dict(self, row: OutlookMaterial) -> dict:
        return {
            "id":            row.id,
            "plan_year":     row.plan_year,
            "original_name": row.original_name,
            "content_type":  row.content_type,
            "file_size":     row.file_size,
            "uploaded_by":   row.uploaded_by,
            "created_at":    row.created_at.isoformat() if row.created_at else None,
        }
