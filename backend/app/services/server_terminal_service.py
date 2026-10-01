"""
Server Control terminal — an interactive SSH shell, opened from the dashboard.

Why this exists at all: a web page cannot launch PuTTY, cmd or PowerShell.
That is a browser security boundary, not a missing feature. So the shell is
brought to the page instead of the page launching a shell.

The security shape is deliberately better than the workflow it replaces, not
worse. To reach a server today an engineer reveals the password into the
browser, copies it to the clipboard, and pastes it into a terminal — the secret
passes through two places we do not control. Here the password is decrypted in
the backend, handed straight to paramiko, and never leaves the process: the
browser only ever sees terminal bytes.

What it does add is a shell reachable over HTTP, so three fences:

  1. The router that issues tickets is behind require_role(Roles.IT), the same
     gate as the rest of Server Control.
  2. A ticket is single-use, expires in TICKET_TTL seconds, and is bound to one
     user and one credential. It is consumed by the first WebSocket frame, NOT
     passed in the URL — a URL would end up in nginx's access log and in
     browser history.
  3. Every session opened is written to ServerCredentialAccessLog, the same
     audit trail a password reveal writes to, so "who got a shell on what" is
     answerable from one place.

Tickets live in Redis rather than a module dict because single-use has to mean
single-use: with more than one worker process an in-memory ticket would be
redeemable once per worker.
"""
import asyncio
import json
import secrets
from typing import Optional

import paramiko
import redis.asyncio as aioredis
import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

# Long enough to survive a slow page and a user who has to re-focus the window,
# short enough that a leaked ticket is worthless by the time anyone finds it.
TICKET_TTL = 30
_TICKET_PREFIX = "server-terminal:ticket:"

# Bytes read from the channel per pump iteration. Terminal output arrives in
# small bursts; a big buffer only adds latency to the common case.
_READ_SIZE = 4096
# Guards against a wedged or flooding session holding a worker forever.
_IDLE_TIMEOUT = 3600


def _redis():
    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def issue_ticket(credential_id: int, username: str) -> str:
    """Mint a single-use ticket for one credential, for one user."""
    ticket = secrets.token_urlsafe(32)
    r = _redis()
    try:
        await r.set(
            _TICKET_PREFIX + ticket,
            json.dumps({"credential_id": credential_id, "user": username}),
            ex=TICKET_TTL,
        )
    finally:
        await r.aclose()
    return ticket


async def redeem_ticket(ticket: str) -> Optional[dict]:
    """Consume a ticket, returning its payload once and only once.

    GETDEL makes redemption atomic — two WebSockets racing with the same
    ticket cannot both win.
    """
    if not ticket:
        return None
    r = _redis()
    try:
        raw = await r.getdel(_TICKET_PREFIX + ticket)
    finally:
        await r.aclose()
    return json.loads(raw) if raw else None


async def resolve_target(db, credential_id: int, accessed_by: str) -> Optional[dict]:
    """Everything needed to open the shell, plus the audit row that records it.

    The audit write happens here rather than at the WebSocket layer so a session
    cannot be opened without being logged: the only way to get the password out
    of this function is to also have written the log entry, in the same commit.

    Returns None when the credential is gone, or when the server has no address
    to connect to — a web console row (an https URL) is not an SSH target and
    says so rather than failing deep inside paramiko.
    """
    from app.models.server_registry import (
        ServerCredential, ServerCredentialAccessLog, ServerEntry,
    )
    from app.services import crypto

    cred = await db.get(ServerCredential, credential_id)
    if cred is None:
        return None
    server = await db.get(ServerEntry, cred.server_id)
    if server is None:
        return None

    host = (server.address or "").strip()
    if not host or "://" in host or "/" in host:
        return {"error": (
            f"'{server.name}' tersimpan sebagai alamat web ({host or 'kosong'}), bukan host SSH. "
            "Buka lewat link alamatnya, atau isi kolom address dengan IP/hostname saja."
        )}
    if not cred.username:
        return {"error": f"Kredensial '{cred.label or credential_id}' belum punya username."}

    db.add(ServerCredentialAccessLog(
        credential_id=cred.id, server_name=server.name,
        credential_label=f"{cred.label or ''} (terminal)".strip(),
        accessed_by=accessed_by,
    ))
    await db.commit()

    return {
        "host": host,
        "port": server.ssh_port or 22,
        "username": cred.username,
        "password": crypto.decrypt(cred.secret_encrypted),
        "server_name": server.name,
        "label": cred.label,
    }


class SshSession:
    """A paramiko shell channel, wrapped for use from async code.

    paramiko is blocking and has no asyncio support, so every call that can
    block is pushed to the default executor. The channel is put in non-blocking
    mode and polled with a short sleep instead of a blocking recv, because a
    blocking recv in an executor thread cannot be cancelled when the WebSocket
    goes away — it would leak a thread per closed tab.
    """

    def __init__(self, host: str, port: int, username: str, password: str):
        self.host, self.port = host, port
        self.username, self.password = username, password
        self._client: Optional[paramiko.SSHClient] = None
        self._chan = None

    async def connect(self, cols: int = 80, rows: int = 24):
        def _open():
            client = paramiko.SSHClient()
            # The inventory is internal infrastructure reached by IP, and we
            # hold no known_hosts for it. AutoAddPolicy matches what
            # ebs_backup/ssh_executor.py already does for the same estate.
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=self.host, port=self.port,
                username=self.username, password=self.password,
                timeout=15, allow_agent=False, look_for_keys=False,
            )
            chan = client.invoke_shell(term="xterm-256color", width=cols, height=rows)
            chan.setblocking(False)
            return client, chan

        loop = asyncio.get_running_loop()
        self._client, self._chan = await loop.run_in_executor(None, _open)

    async def read(self) -> Optional[bytes]:
        """Next chunk of output, or None once the remote shell has exited."""
        while True:
            if self._chan is None:
                return None
            if self._chan.recv_ready():
                return self._chan.recv(_READ_SIZE)
            if self._chan.exit_status_ready() and not self._chan.recv_ready():
                return None
            await asyncio.sleep(0.02)

    def write(self, data: str):
        if self._chan is not None:
            self._chan.send(data)

    def resize(self, cols: int, rows: int):
        if self._chan is not None:
            self._chan.resize_pty(width=cols, height=rows)

    def close(self):
        for obj in (self._chan, self._client):
            try:
                if obj is not None:
                    obj.close()
            except Exception:
                pass
        self._chan = self._client = None
