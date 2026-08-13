"""
HR Organization Structure Router
Route prefix : /api/v1/dashboard/hr/org-structure
Manually curated org chart (add/edit/delete), separate from the Employee
table's auto-derived level/department-based supervisor_id — this is the
source of truth for the Organization Chart tab.
"""
import io
import re
from datetime import datetime, date
from typing import Optional

import openpyxl
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Query
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role, CurrentUser, Roles
from app.models.org_structure import OrgStructureNode, OrgStructureUploadLog
from app.services.department_taxonomy import clean_department_list

router = APIRouter()

# Left-to-right branch order at the top of the chart — matches "Organization
# Structure CKDOTTO.xlsx" and the department order in the Daftar Karyawan
# template. Anything not listed sorts after these, alphabetically.
DEPARTMENT_ORDER = {
    "Board of Commissioners": 0,
    "Board of Directors": 1,
    "Sales & Marketing": 2,
    "Strategy & Development": 3,
    "Plant": 4,
    "Administration": 5,
}

# The source "Daftar Karyawan" Excel template still uses "Strategy
# Development" (no ampersand) and the Indonesian terms below — translated
# on import so the chart stays consistent with the canonical department
# names used everywhere else (Employee/Attendance modules) even
# after a future re-import.
_DEPARTMENT_TRANSLATIONS = {
    "Dewan Komisaris": "Board of Commissioners",
    "Direksi": "Board of Directors",
    "Strategy Development": "Strategy & Development",
}


def _node_dict(n: OrgStructureNode) -> dict:
    return {
        "id": n.id,
        "full_name": n.full_name,
        "position": n.position,
        "department": n.department,
        "division": n.division,
        "sub_team": n.sub_team,
        "join_date": n.join_date.isoformat() if n.join_date else None,
        "supervisor_id": n.supervisor_id,
        "sort_order": n.sort_order,
    }


# ── CRUD ──────────────────────────────────────────────────────────────────

class NodeUpsert(BaseModel):
    full_name: str
    position: Optional[str] = None
    department: Optional[str] = None
    division: Optional[str] = None
    sub_team: Optional[str] = None
    join_date: Optional[str] = None  # YYYY-MM-DD
    supervisor_id: Optional[int] = None
    sort_order: Optional[int] = None


def _parse_join_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


@router.get("/list")
async def list_nodes(
    search: str = Query(""),
    department: Optional[str] = Query(None),
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    """Flat list for the Manage Structure admin table."""
    q = select(OrgStructureNode)
    if search:
        term = f"%{search}%"
        q = q.where(OrgStructureNode.full_name.ilike(term) | OrgStructureNode.position.ilike(term))
    if department:
        q = q.where(OrgStructureNode.department == department)
    q = q.order_by(OrgStructureNode.sort_order, OrgStructureNode.full_name)
    result = await db.execute(q)
    nodes = result.scalars().all()

    sup_ids = {n.supervisor_id for n in nodes if n.supervisor_id}
    sup_names = {}
    if sup_ids:
        sup_result = await db.execute(select(OrgStructureNode.id, OrgStructureNode.full_name).where(OrgStructureNode.id.in_(sup_ids)))
        sup_names = {r[0]: r[1] for r in sup_result.fetchall()}

    return [{**_node_dict(n), "supervisor_name": sup_names.get(n.supervisor_id)} for n in nodes]


@router.get("/lov")
async def get_lov(
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    """Lightweight id/name/department list — for the supervisor picker in the add/edit form."""
    result = await db.execute(
        select(OrgStructureNode.id, OrgStructureNode.full_name, OrgStructureNode.department)
        .order_by(OrgStructureNode.full_name)
    )
    return [{"id": r[0], "full_name": r[1], "department": r[2]} for r in result.fetchall()]


@router.get("/departments")
async def get_departments(
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    result = await db.execute(select(OrgStructureNode.department).distinct())
    depts = clean_department_list(r[0] for r in result.fetchall())
    return sorted(depts, key=lambda d: (DEPARTMENT_ORDER.get(d, 99), d))


# ── LOV for the Add/Edit Position form's free-text fields — every distinct
# value already in use, so HR picks from existing values instead of
# retyping variants that then fragment the chart (the exact "Strategy
# Development" vs "Strategy & Development" class of bug fixed 2026-08-12
# for Employee.department/team). Reuses clean_department_list's generic
# blank/digit-junk filter + case-dedup, not just for department names. ────

@router.get("/positions")
async def get_positions(
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    result = await db.execute(select(OrgStructureNode.position).distinct())
    return clean_department_list(r[0] for r in result.fetchall())


@router.get("/divisions")
async def get_divisions(
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    result = await db.execute(select(OrgStructureNode.division).distinct())
    return clean_department_list(r[0] for r in result.fetchall())


@router.get("/sub-teams")
async def get_sub_teams(
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    result = await db.execute(select(OrgStructureNode.sub_team).distinct())
    return clean_department_list(r[0] for r in result.fetchall())


@router.get("/tree")
async def get_tree(
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    """Full hierarchy nested by supervisor_id, each level sorted by sort_order —
    powers the visual chart. Returns a single root (or a synthetic 'Unassigned'
    wrapper if more than one true root exists)."""
    result = await db.execute(select(OrgStructureNode).order_by(OrgStructureNode.sort_order, OrgStructureNode.full_name))
    rows = result.scalars().all()
    if not rows:
        return {"total": 0, "root": None}

    by_id = {n.id: {**_node_dict(n), "children": []} for n in rows}
    roots = []
    for n in rows:
        node = by_id[n.id]
        if n.supervisor_id and n.supervisor_id in by_id and n.supervisor_id != n.id:
            by_id[n.supervisor_id]["children"].append(node)
        else:
            roots.append(node)

    for node in by_id.values():
        node["children"].sort(key=lambda c: (c["sort_order"], c["full_name"] or ""))

    if len(roots) == 1:
        main_root = roots[0]
    else:
        roots.sort(key=lambda r: (r["sort_order"], r["full_name"] or ""))
        main_root = {
            "id": None, "full_name": "Organization", "position": None,
            "department": None, "division": None, "sub_team": None,
            "join_date": None, "supervisor_id": None, "sort_order": 0,
            "children": roots,
        }

    return {"total": len(rows), "root": main_root}


@router.post("")
async def create_node(
    body: NodeUpsert,
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    if body.supervisor_id:
        sup = await db.scalar(select(OrgStructureNode).where(OrgStructureNode.id == body.supervisor_id))
        if not sup:
            raise HTTPException(404, f"Supervisor id {body.supervisor_id} not found")

    sort_order = body.sort_order
    if sort_order is None:
        # Append after the last existing sibling under the same supervisor.
        sib_q = select(OrgStructureNode.sort_order).where(OrgStructureNode.supervisor_id == body.supervisor_id)
        sib_max = (await db.execute(sib_q)).scalars().all()
        sort_order = (max(sib_max) + 1) if sib_max else DEPARTMENT_ORDER.get(body.department, 50) * 1000

    node = OrgStructureNode(
        full_name=body.full_name, position=body.position, department=body.department,
        division=body.division, sub_team=body.sub_team, join_date=_parse_join_date(body.join_date),
        supervisor_id=body.supervisor_id, sort_order=sort_order,
    )
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
    node = await db.scalar(select(OrgStructureNode).where(OrgStructureNode.id == node_id))
    if not node:
        raise HTTPException(404, "Node not found")

    if body.supervisor_id:
        if body.supervisor_id == node_id:
            raise HTTPException(400, "A node cannot be its own supervisor")
        sup = await db.scalar(select(OrgStructureNode).where(OrgStructureNode.id == body.supervisor_id))
        if not sup:
            raise HTTPException(404, f"Supervisor id {body.supervisor_id} not found")
        # Walk the chain upward — if it reaches node_id again, this would create a loop.
        cursor = sup.supervisor_id
        seen = {node_id}
        hops = 0
        while cursor and hops < 200:
            if cursor in seen:
                raise HTTPException(400, "This assignment would create a reporting-line loop")
            seen.add(cursor)
            cursor = await db.scalar(select(OrgStructureNode.supervisor_id).where(OrgStructureNode.id == cursor))
            hops += 1

    node.full_name = body.full_name
    node.position = body.position
    node.department = body.department
    node.division = body.division
    node.sub_team = body.sub_team
    node.join_date = _parse_join_date(body.join_date)
    node.supervisor_id = body.supervisor_id
    if body.sort_order is not None:
        node.sort_order = body.sort_order
    await db.flush()
    return _node_dict(node)


@router.delete("/{node_id}")
async def delete_node(
    node_id: int,
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    node = await db.scalar(select(OrgStructureNode).where(OrgStructureNode.id == node_id))
    if not node:
        raise HTTPException(404, "Node not found")

    # Re-parent children to this node's own supervisor instead of orphaning
    # their subtree when a middle-of-the-chart node is removed.
    children_result = await db.execute(select(OrgStructureNode).where(OrgStructureNode.supervisor_id == node_id))
    children = children_result.scalars().all()
    for c in children:
        c.supervisor_id = node.supervisor_id

    await db.delete(node)
    await db.flush()
    return {"message": "Deleted", "reparented": len(children)}


# ── Excel import ──────────────────────────────────────────────────────────
# Expected columns (header row 1, data from row 2), matching the "Daftar
# Karyawan" template: No, Departemen, Divisi/Tim, Wilayah/Sub-Tim, Nama,
# Posisi, Tanggal Bergabung, Atasan Langsung (supervisor referenced BY NAME).

_HEADER_ALIASES = {
    "departemen": "department", "divisi/tim": "division", "wilayah/sub-tim": "sub_team",
    "nama": "full_name", "posisi": "position", "tanggal bergabung": "join_date",
    "atasan langsung": "supervisor_name",
}


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _parse_month_year(s) -> Optional[date]:
    s = str(s or "").strip()
    if not s or s == "-":
        return None
    try:
        return datetime.strptime(s, "%b %Y").date()
    except ValueError:
        pass
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


@router.post("/import")
async def import_structure(
    file:  UploadFile = File(...),
    notes: str        = Form(""),
    db:    AsyncSession = Depends(get_db),
    user:  CurrentUser  = Depends(require_role(Roles.HR)),
):
    """Upload the Daftar Karyawan template. REPLACE — all existing org structure
    nodes are deleted and replaced with the file's content."""
    if not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "File must be .xlsx or .xlsm format")

    contents = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
    except Exception as e:
        raise HTTPException(400, f"Invalid Excel file: {e}")

    if not rows:
        raise HTTPException(422, "File is empty")

    header_map = {}
    for idx, v in enumerate(rows[0]):
        key = _HEADER_ALIASES.get(_norm(v))
        if key:
            header_map[key] = idx

    required = {"full_name", "department", "supervisor_name"}
    if not required.issubset(header_map):
        raise HTTPException(422, f"Missing required columns: {required - set(header_map)}")

    def cell(row, field):
        idx = header_map.get(field)
        return row[idx] if idx is not None and idx < len(row) else None

    parsed = []
    for row in rows[1:]:
        name = str(cell(row, "full_name") or "").strip()
        if not name:
            continue
        raw_department = str(cell(row, "department") or "").strip() or None
        parsed.append({
            "full_name":       name,
            "position":        (str(cell(row, "position") or "").strip() or None),
            "department":      _DEPARTMENT_TRANSLATIONS.get(raw_department, raw_department),
            "division":        (str(cell(row, "division") or "").strip() or None) if str(cell(row, "division") or "").strip() not in ("", "-") else None,
            "sub_team":        (str(cell(row, "sub_team") or "").strip() or None) if str(cell(row, "sub_team") or "").strip() not in ("", "-") else None,
            "join_date":       _parse_month_year(cell(row, "join_date")),
            "supervisor_name": (str(cell(row, "supervisor_name") or "").strip() or None),
        })

    if not parsed:
        raise HTTPException(422, "No data rows found (need at least Nama/Departemen/Atasan Langsung filled in)")

    # Assign sort_order = department rank * 1000 + original row order, so
    # left-to-right / top-to-bottom order follows the file (and DEPARTMENT_ORDER
    # for anything not explicitly ranked).
    for i, p in enumerate(parsed):
        p["sort_order"] = DEPARTMENT_ORDER.get(p["department"], 50) * 1000 + i

    # name -> row (for supervisor resolution) — the file also uses "Board of
    # Commissioners" (a body, not a named person) as a supervisor reference for
    # the President Director, aliased to the Board of Commissioners placeholder row.
    name_to_row = {p["full_name"]: p for p in parsed}
    for p in parsed:
        if p["department"] == "Board of Commissioners" and "Board of Commissioners" not in name_to_row:
            name_to_row["Board of Commissioners"] = p

    batch_id = f"batch_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    # REPLACE — delete all previous nodes, replace with the new file's content.
    await db.execute(delete(OrgStructureNode))
    await db.flush()

    row_to_node = {}
    for p in parsed:
        node = OrgStructureNode(
            full_name=p["full_name"], position=p["position"], department=p["department"],
            division=p["division"], sub_team=p["sub_team"], join_date=p["join_date"],
            sort_order=p["sort_order"],
        )
        db.add(node)
        row_to_node[id(p)] = node
    await db.flush()

    skipped_supervisors = set()
    for p in parsed:
        sup_name = p["supervisor_name"]
        if not sup_name or sup_name == "-":
            continue
        sup_row = name_to_row.get(sup_name)
        if not sup_row:
            skipped_supervisors.add(sup_name)
            continue
        row_to_node[id(p)].supervisor_id = row_to_node[id(sup_row)].id

    log = OrgStructureUploadLog(
        batch_id=batch_id, filename=file.filename, total_rows=len(parsed),
        uploaded_by=user.username or "unknown", notes=notes or None,
    )
    db.add(log)

    return {
        "batch_id": batch_id, "filename": file.filename, "total_rows": len(parsed),
        "unresolved_supervisors": sorted(skipped_supervisors),
        "message": f"Import successful: {len(parsed)} nodes loaded" + (
            f" ({len(skipped_supervisors)} supervisor name(s) not found: {', '.join(sorted(skipped_supervisors))})"
            if skipped_supervisors else ""
        ),
    }


@router.get("/upload-logs")
async def get_upload_logs(
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    result = await db.execute(select(OrgStructureUploadLog).order_by(OrgStructureUploadLog.uploaded_at.desc()).limit(20))
    logs = result.scalars().all()
    return [
        {
            "batch_id": l.batch_id, "filename": l.filename, "total_rows": l.total_rows,
            "uploaded_by": l.uploaded_by, "uploaded_at": l.uploaded_at.isoformat() if l.uploaded_at else None,
            "notes": l.notes,
        }
        for l in logs
    ]
