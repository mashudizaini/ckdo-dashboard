"""
Department Master — canonical department/division/team hierarchy + order.
─────────────────────────────────────────
Single source of truth for the curated (non-alphabetical) display order
Employee Summary and related LOVs use — see app/models/department_master.py
for the schema rationale.

ensure_seeded() only ever inserts once, on an empty table (checked at app
startup, same idempotent pattern as this codebase's other ensure_* seed
functions) — later edits to sequence/name/parent belong to whoever manages
this table (SQL for now; a CRUD UI is a natural follow-up, not built here),
not to a re-run of the seed.
"""
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department_master import DepartmentMaster

logger = structlog.get_logger()

# (name, type, sequence, [children...]) — mirrors the org chart image
# exactly: President Director first (its own type, no siblings), then the
# 4 departments in the given sequence, each with its teams (or divisions,
# for Plant) in the given sequence. Names match the raw Employee.department/
# division/team values already in the database.
_SEED_TREE = [
    ("President Director", "director", 0, []),
    ("Sales & Marketing", "department", 1, [
        ("Sales", "team", 1, []),
        ("Marketing", "team", 2, []),
    ]),
    ("Strategy & Development", "department", 2, [
        ("Global Business", "team", 1, []),
        ("Business Development", "team", 2, []),
        ("Regulatory Affairs", "team", 3, []),
    ]),
    ("Plant", "department", 3, [
        ("Production Management", "division", 1, [
            ("Production", "team", 1, []),
            ("PPWH", "team", 2, []),
            ("Engineering", "team", 3, []),
            ("GA", "team", 4, []),
        ]),
        ("Quality Management", "division", 2, [
            ("QA", "team", 1, []),
            ("QC", "team", 2, []),
            ("Validation", "team", 3, []),
            ("Medical Affair", "team", 4, []),
        ]),
    ]),
    ("Administration", "department", 4, [
        ("Planning & Coordination", "team", 1, []),
        ("Accounting & Tax", "team", 2, []),
        ("Purchasing", "team", 3, []),
        ("IT", "team", 4, []),
        ("HRGA", "team", 5, []),
    ]),
]


async def ensure_seeded():
    """Called once from the app lifespan (see main.py) — opens its own
    session since startup runs outside any request context."""
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        existing = await db.scalar(select(DepartmentMaster.id).limit(1))
        if existing:
            return
        logger.info("department_master_seeding")

        # Flush after each level so child rows can reference their parent's real id.
        async def _insert_level(nodes, parent_id):
            for name, type_, seq, children in nodes:
                row = DepartmentMaster(name=name, type=type_, sequence=seq, parent_id=parent_id)
                db.add(row)
                await db.flush()
                if children:
                    await _insert_level(children, row.id)

        await _insert_level(_SEED_TREE, None)
        await db.commit()
        logger.info("department_master_seeded")


async def get_order_maps(db: AsyncSession) -> dict:
    """One query, three lookup dicts — everything hr_employees.py's summary
    endpoints need to sort by curated order instead of alphabetically:
      - dept_seq:     {department_name: sequence}      (type in director/department)
      - division_seq: {(department_name, division_name): sequence}
      - team_seq:     {(department_name, division_name_or_None, team_name): sequence}
    Falls back to empty dicts (callers then fall back to their own
    alphabetical default) if the table is somehow empty — this must never
    be the reason Employee Summary fails to load."""
    rows = (await db.execute(select(DepartmentMaster))).scalars().all()
    if not rows:
        return {"dept_seq": {}, "division_seq": {}, "team_seq": {}}

    by_id = {r.id: r for r in rows}

    def _dept_of(row) -> Optional[str]:
        """Walk up to the nearest department/director ancestor's name."""
        cur = row
        seen = set()
        while cur.parent_id and cur.parent_id not in seen:
            seen.add(cur.parent_id)
            parent = by_id.get(cur.parent_id)
            if not parent:
                break
            cur = parent
        return cur.name

    dept_seq = {r.name: r.sequence for r in rows if r.type in ("director", "department")}
    division_seq = {}
    team_seq = {}
    for r in rows:
        if r.type == "division":
            parent = by_id.get(r.parent_id)
            if parent:
                division_seq[(parent.name, r.name)] = r.sequence
        elif r.type == "team":
            parent = by_id.get(r.parent_id)
            if not parent:
                continue
            if parent.type == "division":
                grandparent = by_id.get(parent.parent_id)
                dept_name = grandparent.name if grandparent else None
                team_seq[(dept_name, parent.name, r.name)] = r.sequence
            else:
                team_seq[(parent.name, None, r.name)] = r.sequence

    return {"dept_seq": dept_seq, "division_seq": division_seq, "team_seq": team_seq}
