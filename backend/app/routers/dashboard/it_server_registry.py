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
  POST   /credentials/{credential_id}/terminal-ticket — mint a single-use ticket

The interactive shell itself is a WebSocket and lives on ws_router below,
mounted WITHOUT this router's Bearer dependency: a browser's WebSocket API
cannot send an Authorization header, so it authenticates with the ticket
this router issues to an already-authenticated IT user.
"""
import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser, Roles, get_current_user, verify_token

from app.services import server_registry_service as svc
from app.services import server_terminal_service as term

import structlog

logger = structlog.get_logger(__name__)

# CR+LF tanpa escape: berkas ini pernah rusak karena backslash di
# heredoc ikut kolaps saat ditulis lewat SSH.
_EOL = chr(13) + chr(10)

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
    # Server Process / Storage Monitoring (see ServerEntry.monitor_enabled)
    monitor_enabled: bool = False
    monitor_credential_id: Optional[int] = None
    ssh_port: int = 22


@router.post("")
async def create_server(body: ServerRequest, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not body.name.strip():
        raise HTTPException(400, "name is required")
    return await svc.create_server(db, body.name.strip(), body.category, body.address, body.notes, body.sequence,
                                   user.username or "it", body.monitor_enabled, body.ssh_port)


@router.put("/{server_id}")
async def update_server(server_id: int, body: ServerRequest, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not body.name.strip():
        raise HTTPException(400, "name is required")
    try:
        result = await svc.update_server(db, server_id, body.name.strip(), body.category, body.address, body.notes,
                                         body.sequence, body.monitor_enabled, body.monitor_credential_id, body.ssh_port)
    except ValueError as e:
        raise HTTPException(400, str(e))
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


# ── Interactive shell ────────────────────────────────────────────────────
#
# A web page cannot launch PuTTY, cmd or PowerShell — that is a browser
# security boundary. So the shell is brought to the page instead. See
# services/server_terminal_service.py for why this is a better security shape
# than reveal-and-paste, and for the three fences around it.


@router.post("/credentials/{credential_id}/terminal-ticket")
async def create_terminal_ticket(credential_id: int, user: CurrentUser = Depends(get_current_user)):
    """Mint a single-use, 30-second ticket for one credential.

    Issued on this router, so it inherits the IT role gate. The ticket is what
    the WebSocket trusts; it is never put in a URL (nginx logs those).
    """
    ticket = await term.issue_ticket(credential_id, user.username or "unknown")
    return {"ticket": ticket, "expires_in": term.TICKET_TTL}


ws_router = APIRouter()


@ws_router.websocket("/terminal")
async def server_terminal(websocket: WebSocket):
    """Bridge a browser terminal to an SSH shell.

    Protocol, all JSON text frames:
      client -> {"ticket": "...", "cols": 120, "rows": 30}   first frame, required
      server -> {"type": "ready", "server": "...", "user": "..."}
      client -> {"type": "input", "data": "ls
"}
      client -> {"type": "resize", "cols": .., "rows": ..}
      server -> {"type": "output", "data": "..."}
      server -> {"type": "error", "message": "..."} then close
    """
    from app.database import AsyncSessionLocal

    await websocket.accept()
    session: term.SshSession | None = None
    pump: asyncio.Task | None = None
    try:
        # First frame carries the ticket. Anything else and the socket closes
        # without having touched the database.
        try:
            hello = json.loads(await asyncio.wait_for(websocket.receive_text(), timeout=15))
        except (asyncio.TimeoutError, ValueError):
            await websocket.close(code=4401)
            return

        # Identity and role are checked HERE, in code. The WebSocket cannot
        # carry an Authorization header, but that is no reason for the route to
        # be unauthenticated: the same Keycloak token the page already holds is
        # sent in this first frame and verified against JWKS, then the IT role
        # is required exactly as require_role(Roles.IT) would.
        #
        # The ticket is a second, independent fence, not the only one: it binds
        # this socket to ONE credential the user already asked for, and is
        # single-use, so a replayed frame cannot open a second shell.
        try:
            caller = await verify_token(hello.get("token", ""))
        except Exception:
            await websocket.send_json({"type": "error", "message": "Sesi login tidak valid, muat ulang halaman."})
            await websocket.close(code=4401)
            return
        if not caller.has_any_role(Roles.IT, "admin"):
            logger.warning("server_terminal_forbidden", user=caller.username)
            await websocket.send_json({"type": "error", "message": "Terminal server hanya untuk tim IT."})
            await websocket.close(code=4403)
            return

        payload = await term.redeem_ticket(hello.get("ticket", ""))
        if payload is None:
            await websocket.send_json({"type": "error", "message": "Sesi kedaluwarsa, tutup lalu buka lagi."})
            await websocket.close(code=4401)
            return

        # A valid ticket is not enough: it must be the ticket this user minted.
        # Otherwise one IT user could redeem another's, and the audit row would
        # name the wrong person.
        if payload.get("user") != (caller.username or "unknown"):
            logger.warning("server_terminal_ticket_mismatch",
                           token_user=caller.username, ticket_user=payload.get("user"))
            await websocket.send_json({"type": "error", "message": "Tiket bukan milik sesi ini."})
            await websocket.close(code=4403)
            return

        cols = int(hello.get("cols") or 80)
        rows = int(hello.get("rows") or 24)

        async with AsyncSessionLocal() as db:
            target = await term.resolve_target(db, payload["credential_id"], payload["user"])
        if target is None:
            await websocket.send_json({"type": "error", "message": "Kredensial tidak ditemukan."})
            await websocket.close(code=4404)
            return
        if "error" in target:
            await websocket.send_json({"type": "error", "message": target["error"]})
            await websocket.close(code=4400)
            return

        session = term.SshSession(target["host"], target["port"], target["username"], target["password"])
        try:
            await session.connect(cols=cols, rows=rows)
        except Exception as e:
            # paramiko's own text is the most useful thing we can say here
            # (auth failed vs timed out vs refused), so pass it through — but
            # "Authentication failed." on its own leaves the reader guessing
            # which of the two likely causes it is, and both are fixable only
            # outside this screen.
            hint = ""
            if "Authentication failed" in str(e):
                hint = (f" Password tersimpan untuk '{target['username']}' ditolak server. "
                        "Periksa kredensialnya di Server Control — atau, kalau ini akun root, "
                        "host-nya mungkin memang menolak login root dengan password "
                        "(PermitRootLogin prohibit-password, bawaan Ubuntu), sehingga kredensial "
                        "itu tidak akan pernah bisa dipakai lewat SSH.")
            logger.warning("server_terminal_connect_failed", user=payload["user"],
                           host=target["host"], ssh_user=target["username"], error=str(e))
            await websocket.send_json({"type": "error", "message": f"Gagal menyambung: {e}{hint}"})
            await websocket.close(code=4500)
            return

        logger.info("server_terminal_opened", user=payload["user"],
                    server=target["server_name"], host=target["host"], ssh_user=target["username"])
        await websocket.send_json({
            "type": "ready", "server": target["server_name"],
            "user": target["username"], "host": target["host"], "label": target["label"],
        })

        async def shell_to_browser():
            while True:
                chunk = await session.read()
                if chunk is None:
                    break
                await websocket.send_json({"type": "output", "data": chunk.decode("utf-8", "replace")})
            await websocket.send_json({"type": "output", "data": _EOL + "[sesi berakhir]" + _EOL})

        pump = asyncio.create_task(shell_to_browser())

        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if msg.get("type") == "input":
                session.write(msg.get("data", ""))
            elif msg.get("type") == "resize":
                session.resize(int(msg.get("cols") or cols), int(msg.get("rows") or rows))
            if pump.done():
                break

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("server_terminal_failed")
    finally:
        if pump is not None:
            pump.cancel()
        if session is not None:
            session.close()
