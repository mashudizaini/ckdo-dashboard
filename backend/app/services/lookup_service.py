"""
Common Lookup — small master data lists in one place (Oracle EBS
FND_LOOKUP_TYPES / FND_LOOKUP_VALUES style); see app/models/lookup.py.

ensure_seeded() runs at app startup: it creates the two tables when missing
(on DEV/PROD create_all only runs in development, so a new model table
would otherwise need sync_schema.py) and inserts each seeded type/value
that isn't there yet. It never updates or deletes a row that exists, so
edits made later through the API are kept across restarts.
"""
from datetime import date
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lookup import LookupType, LookupValue

logger = structlog.get_logger()

MARKET_BUSINESS_TYPE = "EIS_MARKET_BUSINESS_TYPE"

# lookup_type -> (meaning, description, module, [(code, meaning, tag), ...])
_SEED = {
    MARKET_BUSINESS_TYPE: (
        "Sales market → business type",
        "Business type (Local / CMO & Others / Export) each Sales_Ledger market belongs to. "
        "meaning = the market as written in the ledger, tag = its business type.",
        "EIS",
        [
            ("PUBLIC", "Public", "Local"),
            ("PRIVATE", "Private", "Local"),
            ("CMO", "CMO", "CMO & Others"),
            ("SERVICE_AGREEMENT", "Service Agreement", "CMO & Others"),
            ("DOSSIER_FEE", "Dossier Fee", "CMO & Others"),
            ("EXPORT", "Export", "Export"),
            ("EXPORT_ALGERIA", "Export Algeria", "Export"),
            ("EXPORT_PHILIPPINES", "Export Philippines", "Export"),
            ("EXPORT_THAILAND", "Export Thailand", "Export"),
            ("EXPORT_KOREA", "Export Korea", "Export"),
            ("EXPORT_MYANMAR", "Export Myanmar", "Export"),
            ("EXPORT_VIETNAM", "Export Vietnam", "Export"),
        ],
    ),
}


async def ensure_seeded():
    """Called once from the app lifespan (see main.py)."""
    from app.database import AsyncSessionLocal, async_engine, Base

    async with async_engine.begin() as conn:
        await conn.run_sync(lambda sc: Base.metadata.create_all(
            sc, tables=[LookupType.__table__, LookupValue.__table__]))

    async with AsyncSessionLocal() as db:
        added = 0
        for ltype, (meaning, desc, module, values) in _SEED.items():
            if not await db.get(LookupType, ltype):
                db.add(LookupType(lookup_type=ltype, meaning=meaning, description=desc,
                                  module=module, created_by="seed", updated_by="seed"))
                await db.flush()
            have = set((await db.execute(
                select(LookupValue.lookup_code).where(LookupValue.lookup_type == ltype)
            )).scalars())
            for seq, (code, val_meaning, tag) in enumerate(values, start=1):
                if code not in have:
                    db.add(LookupValue(lookup_type=ltype, lookup_code=code, meaning=val_meaning, tag=tag,
                                       display_sequence=seq, enabled_flag=True,
                                       created_by="seed", updated_by="seed"))
                    added += 1
        await db.commit()
        if added:
            logger.info("lookup_values_seeded", added=added)


def _in_effect(v: LookupValue, today: date) -> bool:
    return (v.enabled_flag
            and (v.start_date_active is None or v.start_date_active <= today)
            and (v.end_date_active is None or v.end_date_active >= today))


async def get_values(db: AsyncSession, lookup_type: str, active_only: bool = True) -> list[LookupValue]:
    rows = (await db.execute(
        select(LookupValue).where(LookupValue.lookup_type == lookup_type)
        .order_by(LookupValue.display_sequence, LookupValue.meaning)
    )).scalars().all()
    if not active_only:
        return list(rows)
    today = date.today()
    return [v for v in rows if _in_effect(v, today)]


async def tag_map(db: AsyncSession, lookup_type: str) -> dict[str, str]:
    """{UPPER(meaning) and UPPER(code): tag} for the values in effect — for
    mapping lookups such as market -> business type, matched without
    regard to case."""
    out = {}
    for v in await get_values(db, lookup_type):
        if v.tag:
            out[v.meaning.strip().upper()] = v.tag
            out[v.lookup_code.strip().upper()] = v.tag
    return out


def value_dict(v: LookupValue) -> dict:
    return {
        "id": v.id, "lookup_type": v.lookup_type, "lookup_code": v.lookup_code,
        "meaning": v.meaning, "description": v.description, "tag": v.tag,
        "display_sequence": v.display_sequence, "enabled_flag": v.enabled_flag,
        "start_date_active": v.start_date_active.isoformat() if v.start_date_active else None,
        "end_date_active": v.end_date_active.isoformat() if v.end_date_active else None,
        "updated_by": v.updated_by,
        "updated_at": v.updated_at.isoformat() if v.updated_at else None,
    }


def type_dict(t: LookupType, count: Optional[int] = None) -> dict:
    return {"lookup_type": t.lookup_type, "meaning": t.meaning, "description": t.description,
            "module": t.module, "value_count": count}
