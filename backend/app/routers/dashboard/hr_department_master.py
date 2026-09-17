"""
HR Department Master Router
Route prefix : /api/v1/dashboard/hr/department-master

CRUD for department_master — the curated department/division/team hierarchy
+ display order that Employee Summary and the department_master-sourced LOVs
(Employee List / Turnover Report's Department filter, /teams, etc.) read
from. Previously SQL-only (see department_master_service.py's own
docstring); this is that table's "natural follow-up" CRUD UI.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role, CurrentUser, Roles
from app.models.department_master import DepartmentMaster

router = APIRouter()

TYPES = ("director", "department", "division", "team")


def _node_dict(n: DepartmentMaster) -> dict:
    return {
        "id": n.id,
        "name": n.name,
        "type": n.type,
        "parent_id": n.parent_id,
        "sequence": n.sequence,
    }


class NodeUpsert(BaseModel):
    name: str
    type: str
    parent_id: Optional[int] = None
    sequence: int = 0


@router.get("/tree")
async def get_tree(
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    """Full hierarchy nested by parent_id, each level sorted by sequence —
    powers the management page's tree view."""
    result = await db.execute(select(DepartmentMaster).order_by(DepartmentMaster.sequence, DepartmentMaster.name))
    rows = result.scalars().all()

    by_id = {n.id: {**_node_dict(n), "children": []} for n in rows}
    roots = []
    for n in rows:
        node = by_id[n.id]
        if n.parent_id and n.parent_id in by_id:
            by_id[n.parent_id]["children"].append(node)
        else:
            roots.append(node)

    for node in by_id.values():
        node["children"].sort(key=lambda c: (c["sequence"], c["name"]))
    roots.sort(key=lambda r: (r["sequence"], r["name"]))

    return {"total": len(rows), "roots": roots}


@router.get("/list")
async def list_nodes(
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    """Flat list with parent_name resolved — powers the admin table."""
    result = await db.execute(select(DepartmentMaster).order_by(DepartmentMaster.sequence, DepartmentMaster.name))
    nodes = result.scalars().all()
    by_id = {n.id: n.name for n in nodes}
    return [{**_node_dict(n), "parent_name": by_id.get(n.parent_id)} for n in nodes]


@router.get("/lov")
async def get_lov(
    type: Optional[str] = Query(None, description="Filter to only this type, e.g. for a parent picker"),
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    """Lightweight id/name/type list — for the parent picker in the add/edit form."""
    q = select(DepartmentMaster.id, DepartmentMaster.name, DepartmentMaster.type).order_by(DepartmentMaster.sequence, DepartmentMaster.name)
    if type:
        q = q.where(DepartmentMaster.type == type)
    result = await db.execute(q)
    return [{"id": r[0], "name": r[1], "type": r[2]} for r in result.fetchall()]


@router.post("")
async def create_node(
    body: NodeUpsert,
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    if not body.name.strip():
        raise HTTPException(400, "Name is required")
    if body.type not in TYPES:
        raise HTTPException(400, f"Type must be one of: {', '.join(TYPES)}")
    if body.parent_id:
        parent = await db.scalar(select(DepartmentMaster).where(DepartmentMaster.id == body.parent_id))
        if not parent:
            raise HTTPException(404, f"Parent id {body.parent_id} not found")

    node = DepartmentMaster(name=body.name.strip(), type=body.type, parent_id=body.parent_id, sequence=body.sequence)
    db.add(node)
    await db.flush()
    return _node_dict(node)


@router.put("/{node_id}")
async def update_node(
    node_id: int,
    body: NodeUpsert,
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    node = await db.scalar(select(DepartmentMaster).where(DepartmentMaster.id == node_id))
    if not node:
        raise HTTPException(404, "Node not found")
    if not body.name.strip():
        raise HTTPException(400, "Name is required")
    if body.type not in TYPES:
        raise HTTPException(400, f"Type must be one of: {', '.join(TYPES)}")

    if body.parent_id:
        if body.parent_id == node_id:
            raise HTTPException(400, "A node cannot be its own parent")
        parent = await db.scalar(select(DepartmentMaster).where(DepartmentMaster.id == body.parent_id))
        if not parent:
            raise HTTPException(404, f"Parent id {body.parent_id} not found")
        # Walk the chain upward — if it reaches node_id again, this would create a loop.
        cursor = parent.parent_id
        seen = {node_id}
        hops = 0
        while cursor and hops < 50:
            if cursor in seen:
                raise HTTPException(400, "This assignment would create a parent-child loop")
            seen.add(cursor)
            cursor = await db.scalar(select(DepartmentMaster.parent_id).where(DepartmentMaster.id == cursor))
            hops += 1

    node.name = body.name.strip()
    node.type = body.type
    node.parent_id = body.parent_id
    node.sequence = body.sequence
    await db.flush()
    return _node_dict(node)


@router.delete("/{node_id}")
async def delete_node(
    node_id: int,
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    node = await db.scalar(select(DepartmentMaster).where(DepartmentMaster.id == node_id))
    if not node:
        raise HTTPException(404, "Node not found")
    child_count = await db.scalar(select(DepartmentMaster.id).where(DepartmentMaster.parent_id == node_id).limit(1))
    if child_count:
        raise HTTPException(400, "Delete or reassign this node's children first")
    await db.delete(node)
    return {"message": "Deleted"}
