"""
Server Control Service
─────────────────────────────────────────
CRUD for the server inventory + encrypted credentials, and the reveal path
that decrypts a credential (logged every time — see ServerCredentialAccessLog).
list_servers()/the server-level reads never decrypt anything; only
reveal_credential() does, and only that one function ever calls crypto.decrypt().
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.server_registry import ServerCredential, ServerCredentialAccessLog, ServerEntry
from app.services import crypto


def _credential_dict(c: ServerCredential) -> dict:
    """Never includes the decrypted secret — only reveal_credential() does."""
    return {
        "id": c.id, "server_id": c.server_id, "label": c.label, "username": c.username,
        "notes": c.notes, "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _server_dict(s: ServerEntry, credentials: list[ServerCredential]) -> dict:
    return {
        "id": s.id, "name": s.name, "category": s.category, "address": s.address,
        "notes": s.notes, "sequence": s.sequence, "created_by": s.created_by,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        "credentials": [_credential_dict(c) for c in credentials],
    }


async def list_servers(db: AsyncSession) -> list[dict]:
    servers = (await db.execute(
        select(ServerEntry).order_by(ServerEntry.category, ServerEntry.sequence, ServerEntry.name)
    )).scalars().all()
    creds = (await db.execute(select(ServerCredential).order_by(ServerCredential.id))).scalars().all()
    by_server: dict[int, list[ServerCredential]] = {}
    for c in creds:
        by_server.setdefault(c.server_id, []).append(c)
    return [_server_dict(s, by_server.get(s.id, [])) for s in servers]


async def list_categories(db: AsyncSession) -> list[str]:
    rows = (await db.execute(select(ServerEntry.category).distinct())).scalars().all()
    return sorted({r for r in rows if r})


async def create_server(
    db: AsyncSession, name: str, category: str, address: Optional[str],
    notes: Optional[str], sequence: int, created_by: str,
) -> dict:
    s = ServerEntry(name=name, category=category or "Other", address=address, notes=notes,
                     sequence=sequence, created_by=created_by)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return _server_dict(s, [])


async def update_server(
    db: AsyncSession, server_id: int, name: str, category: str, address: Optional[str],
    notes: Optional[str], sequence: int,
) -> Optional[dict]:
    s = await db.get(ServerEntry, server_id)
    if not s:
        return None
    s.name, s.category, s.address, s.notes, s.sequence = name, category or "Other", address, notes, sequence
    s.updated_at = datetime.utcnow()
    await db.commit()
    creds = (await db.execute(select(ServerCredential).where(ServerCredential.server_id == server_id))).scalars().all()
    return _server_dict(s, creds)


async def delete_server(db: AsyncSession, server_id: int) -> bool:
    s = await db.get(ServerEntry, server_id)
    if not s:
        return False
    await db.delete(s)
    await db.commit()
    return True


async def add_credential(
    db: AsyncSession, server_id: int, label: Optional[str], username: Optional[str],
    password: str, notes: Optional[str], created_by: str,
) -> dict:
    c = ServerCredential(
        server_id=server_id, label=label, username=username,
        secret_encrypted=crypto.encrypt(password), notes=notes, created_by=created_by,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return _credential_dict(c)


async def update_credential(
    db: AsyncSession, credential_id: int, label: Optional[str], username: Optional[str],
    password: Optional[str], notes: Optional[str],
) -> Optional[dict]:
    c = await db.get(ServerCredential, credential_id)
    if not c:
        return None
    c.label, c.username, c.notes = label, username, notes
    if password:  # blank = keep existing secret unchanged
        c.secret_encrypted = crypto.encrypt(password)
    c.updated_at = datetime.utcnow()
    await db.commit()
    return _credential_dict(c)


async def delete_credential(db: AsyncSession, credential_id: int) -> bool:
    c = await db.get(ServerCredential, credential_id)
    if not c:
        return False
    await db.delete(c)
    await db.commit()
    return True


async def reveal_credential(db: AsyncSession, credential_id: int, accessed_by: str) -> Optional[dict]:
    c = await db.get(ServerCredential, credential_id)
    if not c:
        return None
    server = await db.get(ServerEntry, c.server_id)
    password = crypto.decrypt(c.secret_encrypted)

    db.add(ServerCredentialAccessLog(
        credential_id=c.id, server_name=server.name if server else None,
        credential_label=c.label, accessed_by=accessed_by,
    ))
    await db.commit()

    return {"id": c.id, "username": c.username, "password": password}


async def list_access_log(db: AsyncSession, limit: int = 200) -> list[dict]:
    rows = (await db.execute(
        select(ServerCredentialAccessLog).order_by(ServerCredentialAccessLog.accessed_at.desc()).limit(limit)
    )).scalars().all()
    return [
        {
            "id": r.id, "credential_id": r.credential_id, "server_name": r.server_name,
            "credential_label": r.credential_label, "accessed_by": r.accessed_by,
            "accessed_at": r.accessed_at.isoformat() if r.accessed_at else None,
        }
        for r in rows
    ]
