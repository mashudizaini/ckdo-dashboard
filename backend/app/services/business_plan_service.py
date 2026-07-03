"""
Business Plan Service — PAC module.
Stores and retrieves Business Plan documents in PostgreSQL.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.business_plan import PACBusinessPlan
import structlog

logger = structlog.get_logger()


class BusinessPlanService:

    # ── List ─────────────────────────────────────────────────────────────────

    async def list_plans(
        self,
        db: AsyncSession,
        plan_year: Optional[int] = None,
        doc_type: Optional[str] = None,
        department: Optional[str] = None,
    ) -> dict:
        q = select(PACBusinessPlan).order_by(
            PACBusinessPlan.plan_year.desc(),
            PACBusinessPlan.doc_type,
            PACBusinessPlan.department,
        )
        if plan_year:
            q = q.where(PACBusinessPlan.plan_year == plan_year)
        if doc_type:
            q = q.where(PACBusinessPlan.doc_type == doc_type)
        if department:
            q = q.where(PACBusinessPlan.department.ilike(f"%{department}%"))

        result = await db.execute(q)
        rows = result.scalars().all()
        return {"success": True, "count": len(rows), "data": [self._to_dict(r) for r in rows]}

    # ── Get single ────────────────────────────────────────────────────────────

    async def get_plan(self, db: AsyncSession, plan_id: int) -> dict:
        row = await db.get(PACBusinessPlan, plan_id)
        if not row:
            return {"success": False, "error": "Not found"}
        return {"success": True, "data": self._to_dict(row)}

    # ── Upsert ───────────────────────────────────────────────────────────────

    async def upsert_plan(self, db: AsyncSession, payload: dict, username: str) -> dict:
        """
        Create or update a Business Plan document.
        Unique key: doc_type + plan_year + department + team_code.
        If id is provided and exists — update that record.
        Otherwise try to find by unique key; if not found — create.
        """
        doc_id = payload.get("id")
        row = None

        if doc_id:
            row = await db.get(PACBusinessPlan, doc_id)

        if not row:
            # Try unique-key lookup
            q = select(PACBusinessPlan).where(
                PACBusinessPlan.doc_type   == payload.get("doc_type"),
                PACBusinessPlan.plan_year  == payload.get("plan_year"),
                PACBusinessPlan.department == (payload.get("department") or "ALL"),
                PACBusinessPlan.team_code  == (payload.get("team_code") or ""),
            )
            result = await db.execute(q)
            row = result.scalar_one_or_none()

        if row:
            row.content    = payload.get("content", row.content)
            row.team_name  = payload.get("team_name",  row.team_name)
            row.plan_role  = payload.get("plan_role",  row.plan_role)
            row.status     = payload.get("status",     row.status)
            row.updated_at = datetime.utcnow()
        else:
            row = PACBusinessPlan(
                doc_type   = payload.get("doc_type", "strategy_plan"),
                plan_year  = payload.get("plan_year", datetime.now().year),
                department = payload.get("department") or "ALL",
                team_code  = payload.get("team_code") or "",
                team_name  = payload.get("team_name") or "",
                plan_role  = payload.get("plan_role") or "",
                content    = payload.get("content", {}),
                status     = payload.get("status", "draft"),
                created_by = username,
            )
            db.add(row)

        await db.flush()
        await db.refresh(row)
        return {"success": True, "data": self._to_dict(row)}

    # ── Delete ────────────────────────────────────────────────────────────────

    async def delete_plan(self, db: AsyncSession, plan_id: int) -> dict:
        row = await db.get(PACBusinessPlan, plan_id)
        if not row:
            return {"success": False, "error": "Not found"}
        await db.execute(delete(PACBusinessPlan).where(PACBusinessPlan.id == plan_id))
        return {"success": True, "message": f"Deleted plan #{plan_id}"}

    # ── Helper ────────────────────────────────────────────────────────────────

    def _to_dict(self, row: PACBusinessPlan) -> dict:
        return {
            "id":          row.id,
            "doc_type":    row.doc_type,
            "plan_year":   row.plan_year,
            "department":  row.department,
            "team_code":   row.team_code,
            "team_name":   row.team_name,
            "plan_role":   row.plan_role,
            "content":     row.content,
            "status":      row.status,
            "created_at":  row.created_at.isoformat() if row.created_at else None,
            "updated_at":  row.updated_at.isoformat() if row.updated_at else None,
            "created_by":  row.created_by,
        }
