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
import re
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


# ── Name matching ──────────────────────────────────────────────────────────
# department_master is edited by hand (Setup > HRGA > Department Master), and
# its names drift from the raw Employee values: "Strategy Development" vs
# "Strategy & Development", "Quality Assurance" vs "QA", "General Affair" vs
# "GA". An exact lookup then misses, and the row silently falls back to
# alphabetical at the bottom. One rule, with a Python and a SQL twin so the
# Summary count and its drill-down list can never disagree:
#   same letters/digits ignoring case, spaces and punctuation, OR
#   one side is the other's initials ("QA" = "Quality Assurance").

_NON_ALNUM = re.compile(r"[^A-Za-z0-9]+")
_ACRONYM_MAX = 5


def name_key(s: Optional[str]) -> str:
    return _NON_ALNUM.sub("", s or "").upper()


def name_acronym(s: Optional[str]) -> str:
    """Initials of a multi-word name ("Planning & Coordination" -> "PC");
    empty for a single word, which has no meaningful initials."""
    words = [w for w in _NON_ALNUM.split(s or "") if w]
    return "".join(w[0] for w in words).upper() if len(words) > 1 else ""


def names_match(a: Optional[str], b: Optional[str]) -> bool:
    ka, kb = name_key(a), name_key(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    if len(ka) <= _ACRONYM_MAX and name_acronym(b) == ka:
        return True
    return len(kb) <= _ACRONYM_MAX and name_acronym(a) == kb


def sql_name_match(col, value: str):
    """SQL twin of names_match(col, value) for PostgreSQL."""
    from sqlalchemy import and_, func, or_

    key = name_key(value)
    col_key = func.upper(func.regexp_replace(col, "[^A-Za-z0-9]+", "", "g"))
    # Initials: first character of each alphanumeric run.
    col_acr = func.upper(func.regexp_replace(col, "[^A-Za-z0-9]*([A-Za-z0-9])[A-Za-z0-9]*", "\1", "g"))
    multi_word = col.op("~")("[A-Za-z0-9][^A-Za-z0-9]+[A-Za-z0-9]")
    conds = [col_key == key]
    if key and len(key) <= _ACRONYM_MAX:
        conds.append(and_(multi_word, col_acr == key))
    acr = name_acronym(value)
    if acr:
        conds.append(and_(func.length(col_key) <= _ACRONYM_MAX, col_key == acr))
    return or_(*conds)


async def get_tree(db: AsyncSession) -> list[dict]:
    """department_master as nested dicts, every level sorted by sequence
    (a division before a team on equal sequence, then name):
    [{id, name, type, sequence, children: [...]}, ...] — top level is the
    director/department rows."""
    rows = (await db.execute(select(DepartmentMaster))).scalars().all()
    nodes = {r.id: {"id": r.id, "name": r.name, "type": r.type, "sequence": r.sequence or 0,
                    "parent_id": r.parent_id, "children": []} for r in rows}
    roots = []
    for n in nodes.values():
        parent = nodes.get(n["parent_id"]) if n["parent_id"] else None
        (parent["children"] if parent else roots).append(n)

    def _sort(lst):
        lst.sort(key=lambda n: (n["sequence"], 0 if n["type"] == "division" else 1, n["name"]))
        for n in lst:
            _sort(n["children"])

    _sort(roots)
    return roots
