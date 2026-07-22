"""
Business Plan Setup Service — PAC module.
Stores and retrieves Business Plan Setup documents (Schedule, Guideline, Outlook) in PostgreSQL.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.business_plan_setup import PACBusinessPlanSetup
import structlog

logger = structlog.get_logger()


class BusinessPlanSetupService:

    # ── List ─────────────────────────────────────────────────────────────────

    async def list_setup(
        self,
        db: AsyncSession,
        setup_module: Optional[str] = None,
        plan_year: Optional[int] = None,
    ) -> dict:
        q = select(PACBusinessPlanSetup).order_by(
            PACBusinessPlanSetup.plan_year.desc(),
            PACBusinessPlanSetup.setup_module,
        )
        if setup_module:
            q = q.where(PACBusinessPlanSetup.setup_module == setup_module)
        if plan_year:
            q = q.where(PACBusinessPlanSetup.plan_year == plan_year)

        result = await db.execute(q)
        rows = result.scalars().all()
        return {"success": True, "count": len(rows), "data": [self._to_dict(r) for r in rows]}

    # ── Get single ────────────────────────────────────────────────────────────

    async def get_setup(self, db: AsyncSession, setup_id: int) -> dict:
        row = await db.get(PACBusinessPlanSetup, setup_id)
        if not row:
            return {"success": False, "error": "Not found"}
        return {"success": True, "data": self._to_dict(row)}

    # ── Upsert ───────────────────────────────────────────────────────────────

    async def upsert_setup(self, db: AsyncSession, payload: dict, username: str) -> dict:
        """
        Create or update a Setup document.
        Unique key: setup_module + plan_year.
        """
        setup_id = payload.get("id")
        row = None

        if setup_id:
            row = await db.get(PACBusinessPlanSetup, setup_id)

        if not row:
            q = select(PACBusinessPlanSetup).where(
                PACBusinessPlanSetup.setup_module == payload.get("setup_module"),
                PACBusinessPlanSetup.plan_year  == payload.get("plan_year"),
            )
            result = await db.execute(q)
            row = result.scalar_one_or_none()

        if row:
            row.content    = payload.get("content", row.content)
            row.status     = payload.get("status",     row.status)
            row.updated_at = datetime.utcnow()
        else:
            row = PACBusinessPlanSetup(
                setup_module = payload.get("setup_module", "schedule"),
                plan_year    = payload.get("plan_year", datetime.now().year),
                content      = payload.get("content", {}),
                status       = payload.get("status", "draft"),
                created_by   = username,
            )
            db.add(row)

        await db.flush()
        await db.refresh(row)
        return {"success": True, "data": self._to_dict(row)}

    # ── Delete ────────────────────────────────────────────────────────────────

    async def delete_setup(self, db: AsyncSession, setup_id: int) -> dict:
        row = await db.get(PACBusinessPlanSetup, setup_id)
        if not row:
            return {"success": False, "error": "Not found"}
        await db.execute(delete(PACBusinessPlanSetup).where(PACBusinessPlanSetup.id == setup_id))
        return {"success": True, "message": f"Deleted setup #{setup_id}"}

    # ── Helper ────────────────────────────────────────────────────────────────

    def _to_dict(self, row: PACBusinessPlanSetup) -> dict:
        return {
            "id":          row.id,
            "setup_module": row.setup_module,
            "plan_year":   row.plan_year,
            "content":     row.content,
            "status":      row.status,
            "created_at":  row.created_at.isoformat() if row.created_at else None,
            "updated_at":  row.updated_at.isoformat() if row.updated_at else None,
            "created_by":  row.created_by,
        }
