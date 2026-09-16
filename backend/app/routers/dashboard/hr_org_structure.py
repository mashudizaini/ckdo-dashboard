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
from sqlalchemy import select, delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_engine
from app.dependencies import require_role, CurrentUser, Roles
from app.models.employee import Employee
from app.models.org_structure import OrgStructureNode, OrgStructureUploadLog
from app.services.department_taxonomy import clean_department_list

router = APIRouter()


async def ensure_employee_id_column():
    """org_structure_nodes already existed before employee_id was added to
    the model — Base.metadata.create_all only creates missing TABLES, it
    never ALTERs an existing one for a new column (see this repo's other
    ensure_* helpers for the same reason), so this runs once at startup."""
    async with async_engine.begin() as conn:
        await conn.execute(text(
            "ALTER TABLE org_structure_nodes ADD COLUMN IF NOT EXISTS employee_id VARCHAR(20)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_org_structure_nodes_employee_id ON org_structure_nodes (employee_id)"
        ))

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
        "employee_id": n.employee_id,
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


@router.get("/employee-search")
async def search_employees_for_fill(
    q:    str          = Query(..., min_length=1),
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    """Read-only lookup into the Employee table for the Add/Edit Position
    form's "Fill from Employee List" button — deliberately just a one-time
    pre-fill of the node form, not a write-side link between
    OrgStructureNode and Employee. Keeping the two decoupled (see this
    module's own docstring) means HR can still adjust a chart entry's
    phrasing/placement afterward without a future Employee edit or a bulk
    sync silently overwriting that curation. Active employees only — this
    is for adding someone who's currently here, not editing legacy/resigned
    chart entries."""
    term = f"%{q}%"
    result = await db.execute(
        select(Employee.user_id, Employee.full_name, Employee.job_title, Employee.department,
               Employee.division, Employee.team, Employee.date_of_joining)
        .where(
            Employee.employment_status == "Active",
            Employee.full_name.ilike(term) | Employee.user_id.ilike(term),
        )
        .order_by(Employee.full_name)
        .limit(15)
    )
    return [
        {
            "user_id": r[0], "full_name": r[1], "job_title": r[2], "department": r[3],
            "division": r[4], "team": r[5],
            "join_date": r[6].isoformat() if r[6] else None,
        }
        for r in result.fetchall()
    ]


def _norm_name(s: Optional[str]) -> str:
    return " ".join((s or "").strip().lower().split())


# (Employee column, OrgStructureNode column) pairs this syncs — every
# descriptive field the two tables have in common.
_SYNC_FIELDS = [
    ("job_title",      "position"),
    ("department",     "department"),
    ("division",       "division"),
    ("team",           "sub_team"),
    ("date_of_joining", "join_date"),
]


def _fuzzy_candidates(node_name_norm: str, emp_rows: list) -> list:
    """LIKE-style fallback for when the exact normalized name doesn't hit
    anything — a lot of chart entries carry an incomplete/abbreviated name
    (e.g. "M. Nur Aidi S" for "Muhammad Nur Aidi Setiawan"), so this checks
    substring containment in both directions instead of requiring an exact
    match. Deliberately simple (no token/initials matching) — a first pass
    per HR's own request, refine later if it's not catching enough."""
    out = []
    for row in emp_rows:
        en = _norm_name(row.full_name)
        if not en:
            continue
        if node_name_norm in en or en in node_name_norm:
            out.append(row)
    return out


@router.post("/sync-from-employees")
async def sync_from_employees(
    db:   AsyncSession = Depends(get_db),
    user: CurrentUser  = Depends(require_role(Roles.HR)),
):
    """Two-phase sync against the Employee master, which is the reference
    for this data:

    Phase 1 — IDENTITY: for every node without an employee_id yet, find its
    Employee by full_name — exact match first, falling back to a LIKE-style
    substring match in either direction (see _fuzzy_candidates) since many
    chart names are incomplete. Exactly one candidate -> link
    node.employee_id to it AND overwrite node.full_name with the Employee's
    real name (Employee is the reference, so unlike every other field this
    one is NOT additive-only — it's corrected every run). More than one
    candidate -> left alone and reported as ambiguous rather than guessing.

    Phase 2 — FIELDS: for every node that has an employee_id (just linked
    above, or already linked from an earlier run), fill in any empty
    position/department/division/sub_team/join_date straight from that
    Employee row by id — reliable now that the identity is confirmed, so
    unlike Phase 1 there's no ambiguity to resolve here. Still additive:
    only touches a field that's currently empty."""
    nodes_result = await db.execute(select(OrgStructureNode))
    nodes = nodes_result.scalars().all()

    emp_result = await db.execute(
        select(Employee.user_id, Employee.full_name, Employee.job_title, Employee.department,
               Employee.division, Employee.team, Employee.date_of_joining)
    )
    emp_rows = emp_result.fetchall()
    by_exact_name: dict[str, list] = {}
    by_user_id: dict[str, object] = {}
    for row in emp_rows:
        by_user_id[row.user_id] = row
        key = _norm_name(row.full_name)
        if key:
            by_exact_name.setdefault(key, []).append(row)

    linked_names, renamed_names, unmatched, ambiguous_identity = [], [], [], []

    # Phase 1 — identity
    for node in nodes:
        if node.employee_id:
            continue
        key = _norm_name(node.full_name)
        candidates = by_exact_name.get(key) or _fuzzy_candidates(key, emp_rows)
        distinct_ids = {c.user_id for c in candidates}
        if not distinct_ids:
            unmatched.append(node.full_name)
            continue
        if len(distinct_ids) > 1:
            ambiguous_identity.append(node.full_name)
            continue
        match = candidates[0]
        node.employee_id = match.user_id
        linked_names.append(node.full_name)
        if node.full_name != match.full_name:
            renamed_names.append(f"{node.full_name} -> {match.full_name}")
            node.full_name = match.full_name

    # Phase 2 — fields, keyed by the now-reliable employee_id link
    updated_names = []
    for node in nodes:
        if not node.employee_id:
            continue
        match = by_user_id.get(node.employee_id)
        if not match:
            continue  # linked to an id no longer in the Employee master
        node_changed = False
        for ef, nf in _SYNC_FIELDS:
            if getattr(node, nf):  # already has a value — never overwrite
                continue
            val = getattr(match, ef)
            if val:
                setattr(node, nf, val)
                node_changed = True
        if node_changed:
            updated_names.append(node.full_name)

    await db.commit()
    return {
        "total_nodes": len(nodes),
        "linked": len(linked_names), "linked_names": linked_names,
        "renamed": len(renamed_names), "renamed_names": renamed_names,
        "field_updated": len(updated_names), "field_updated_names": updated_names,
        "unmatched": unmatched,
        "ambiguous_identity": ambiguous_identity,
    }


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
