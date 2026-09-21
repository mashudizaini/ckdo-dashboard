"""
Server Control Router
Route prefix : /api/v1/dashboard/it/server-registry
Required role: it_staff OR admin — gated at include_router() level in
main.py (same pattern as ebs_backup.py/vpn_monitor.py), since every
endpoint here is IT-only, no mixed-gate endpoints like ebs_chat.py's.

Endpoints:
  GET    /                              — all servers + their credentials (masked, no secrets)
  GET    /categories                    — distinct categories, for the add/edit form
  POST   /                              — create server
  PUT    /{server_id}                   — update server
  DELETE /{server_id}                   — delete server (cascades its credentials)
  POST   /{server_id}/credentials       — add a credential
  PUT    /credentials/{credential_id}   — update a credential (blank password = keep existing)
  DELETE /credentials/{credential_id}   — delete a credential
  POST   /credentials/{credential_id}/reveal — decrypt + return the password, logged
  GET    /access-log                    — recent reveal history (who/what/when)
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser, get_current_user
from app.services import server_registry_service as svc

router = APIRouter()


@router.get("")
async def get_servers(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await svc.list_servers(db)


@router.get("/categories")
async def get_categories(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await svc.list_categories(db)


@router.get("/access-log")
async def get_access_log(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await svc.list_access_log(db)


class ServerRequest(BaseModel):
    name: str
    category: str = "Other"
    address: Optional[str] = None
    notes: Optional[str] = None
    sequence: int = 0


@router.post("")
async def create_server(body: ServerRequest, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not body.name.strip():
        raise HTTPException(400, "name is required")
    return await svc.create_server(db, body.name.strip(), body.category, body.address, body.notes, body.sequence, user.username or "it")


@router.put("/{server_id}")
async def update_server(server_id: int, body: ServerRequest, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not body.name.strip():
        raise HTTPException(400, "name is required")
    result = await svc.update_server(db, server_id, body.name.strip(), body.category, body.address, body.notes, body.sequence)
    if not result:
        raise HTTPException(404, "Server not found")
    return result


@router.delete("/{server_id}")
async def delete_server(server_id: int, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    ok = await svc.delete_server(db, server_id)
    if not ok:
        raise HTTPException(404, "Server not found")
    return {"success": True}


class CredentialRequest(BaseModel):
    label: Optional[str] = None
    username: Optional[str] = None
    password: str
    notes: Optional[str] = None


@router.post("/{server_id}/credentials")
async def add_credential(server_id: int, body: CredentialRequest, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not body.password:
        raise HTTPException(400, "password is required")
    return await svc.add_credential(db, server_id, body.label, body.username, body.password, body.notes, user.username or "it")


class CredentialUpdateRequest(BaseModel):
    label: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None  # blank/omitted = keep existing secret
    notes: Optional[str] = None


@router.put("/credentials/{credential_id}")
async def update_credential(credential_id: int, body: CredentialUpdateRequest, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await svc.update_credential(db, credential_id, body.label, body.username, body.password, body.notes)
    if not result:
        raise HTTPException(404, "Credential not found")
    return result


@router.delete("/credentials/{credential_id}")
async def delete_credential(credential_id: int, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    ok = await svc.delete_credential(db, credential_id)
    if not ok:
        raise HTTPException(404, "Credential not found")
    return {"success": True}


@router.post("/credentials/{credential_id}/reveal")
async def reveal_credential(credential_id: int, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await svc.reveal_credential(db, credential_id, user.username or user.email or "unknown")
    if not result:
        raise HTTPException(404, "Credential not found")
    return result
