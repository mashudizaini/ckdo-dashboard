"""
Oracle EBS attachments — list them, and stream one out for download.

Where the files actually are: NOT loose on the EBS server's filesystem, but
BLOBs inside the database itself (FND_LOBS.FILE_DATA). So this needs no file
share, no SSH to the EBS host and no path mapping — only the Oracle connection
the dashboard already opens. Measured on PROD 2026-10-02: 208,511 files,
~103 GB, average 520 KB, largest 58.8 MB, mostly PDF.

The chain from a business document to its file is four joins:

    fnd_attached_documents   entity_name + pk1_value -> the business row
      -> fnd_documents       datatype_id = 6 means "File" (1/2 are text notes,
                             5 is a URL — none of those are downloadable)
      -> fnd_documents_tl    the title a user typed
      -> fnd_lobs            file_name, content type, and the bytes
                             (joined on fnd_lobs.file_id = fnd_documents.media_id)

Nothing is copied into the dashboard. 103 GB mirrored would double the storage
bill to serve files that are already somewhere durable, and would go stale the
moment someone attaches a document in EBS. Files stream straight through,
read in chunks, so a 59 MB PDF never lands in memory whole.

ALLOWED_ENTITIES is the security boundary and the reason the download endpoint
re-checks it. attached_document_id is a single global sequence across every
attachment in EBS — HR records, payment instructions, expense claims. Without
that check, an endpoint meant for invoice attachments would hand out any of the
208,511 files to anyone who could guess an id, and they are consecutive
integers.
"""
import json
import secrets
from typing import Iterator, Optional

import redis
import structlog

from app.config import get_settings
from app.database import get_oracle_connection

logger = structlog.get_logger(__name__)

# datatype_id 6 = file. The others (1 short text, 2 long text, 5 URL) carry no
# bytes to download, so they never appear in a list of attachments here.
_FILE_DATATYPE = 6

# Entity names a caller may reach, per feature. Keep these narrow: each key is
# one screen's worth of authority, not a general-purpose file reader.
ALLOWED_ENTITIES = {
    "ap_invoice": frozenset({"AP_INVOICES"}),
}

# 1 MB per read. Big enough that a 59 MB file is ~59 round trips rather than
# thousands, small enough that memory stays flat no matter the file.
_CHUNK = 1024 * 1024

_LIST_SQL = """
    SELECT ad.attached_document_id,
           dt.title,
           dt.description,
           l.file_name,
           l.file_content_type,
           DBMS_LOB.GETLENGTH(l.file_data) AS file_size,
           TO_CHAR(ad.creation_date, 'YYYY-MM-DD HH24:MI') AS created_at
    FROM fnd_attached_documents ad
    JOIN fnd_documents      d  ON d.document_id = ad.document_id
                              AND d.datatype_id = :datatype
    JOIN fnd_documents_tl   dt ON dt.document_id = d.document_id
                              AND dt.language = USERENV('LANG')
    JOIN fnd_lobs           l  ON l.file_id = d.media_id
    WHERE ad.entity_name = :entity
      AND ad.pk1_value   = :pk
      AND l.file_data IS NOT NULL
    ORDER BY ad.creation_date DESC
"""

# Deliberately selects entity_name too: the caller compares it against its own
# allowlist before a single byte is read.
_FETCH_SQL = """
    SELECT ad.entity_name, l.file_name, l.file_content_type,
           DBMS_LOB.GETLENGTH(l.file_data) AS file_size, l.file_data
    FROM fnd_attached_documents ad
    JOIN fnd_documents d ON d.document_id = ad.document_id
                        AND d.datatype_id = :datatype
    JOIN fnd_lobs      l ON l.file_id = d.media_id
    WHERE ad.attached_document_id = :aid
      AND l.file_data IS NOT NULL
"""


def list_attachments(entity_name: str, pk_value) -> list[dict]:
    """Attachment metadata for one business row — no file bytes read."""
    with get_oracle_connection() as conn:
        cur = conn.cursor()
        cur.execute(_LIST_SQL, entity=entity_name, pk=str(pk_value), datatype=_FILE_DATATYPE)
        cols = [d[0].lower() for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def open_attachment(attached_document_id: int, scope: str) -> Optional[dict]:
    """Resolve one attachment for download, or None if it is out of scope.

    `scope` names a key in ALLOWED_ENTITIES. An attachment that exists but hangs
    off some other entity returns None exactly like one that does not exist —
    the caller cannot tell the difference, so a probe learns nothing about which
    ids are real.

    The returned `stream` holds its own Oracle connection open until it is
    exhausted or closed, because the LOB cannot outlive its connection.
    """
    allowed = ALLOWED_ENTITIES[scope]

    conn = get_oracle_connection().__enter__()
    try:
        cur = conn.cursor()
        cur.execute(_FETCH_SQL, aid=attached_document_id, datatype=_FILE_DATATYPE)
        row = cur.fetchone()
        if row is None:
            conn.close()
            return None
        entity, file_name, content_type, size, lob = row
        if entity not in allowed:
            logger.warning("ebs_attachment_out_of_scope",
                           attached_document_id=attached_document_id, entity=entity, scope=scope)
            conn.close()
            return None
    except Exception:
        conn.close()
        raise

    def stream() -> Iterator[bytes]:
        # Oracle LOB offsets are 1-based. Closing the connection in `finally`
        # covers the client disconnecting mid-download, which would otherwise
        # leak a session per abandoned transfer.
        try:
            offset = 1
            while offset <= size:
                chunk = lob.read(offset, _CHUNK)
                if not chunk:
                    break
                yield chunk
                offset += len(chunk)
        finally:
            conn.close()

    return {
        "file_name": file_name or f"attachment-{attached_document_id}",
        "content_type": content_type or "application/octet-stream",
        "size": size,
        "stream": stream,
    }


# ── Download tickets, for links handed out in CoChat ─────────────────────
#
# A link in a chat answer cannot carry the dashboard's Bearer token: the person
# clicks it in a plain browser tab with no SPA behind it. So the link carries a
# ticket instead — minted for one attachment, for one person, usable once,
# expiring in minutes.
#
# In Redis rather than a module dict for the same reason the terminal tickets
# are: with more than one worker, an in-memory ticket would be redeemable once
# per worker, and "single use" has to mean it.
_TICKET_PREFIX = "ebs-attachment:ticket:"

# Long enough for someone to read the answer, decide, and click; short enough
# that a link pasted into a group chat is dead before anyone else gets to it.
TICKET_TTL = 600


def _redis():
    return redis.from_url(get_settings().redis_url, decode_responses=True)


def issue_download_ticket(attached_document_id: int, email: str, scope: str) -> str:
    r = _redis()
    try:
        ticket = secrets.token_urlsafe(32)
        r.set(_TICKET_PREFIX + ticket,
              json.dumps({"aid": int(attached_document_id), "email": email, "scope": scope}),
              ex=TICKET_TTL)
        return ticket
    finally:
        r.close()


def redeem_download_ticket(ticket: str) -> Optional[dict]:
    """Consume a ticket, returning its payload once and only once.

    GETDEL makes it atomic: two clicks racing on the same link cannot both win,
    so a forwarded link is spent by whoever gets there first and is then useless.
    """
    if not ticket:
        return None
    r = _redis()
    try:
        raw = r.getdel(_TICKET_PREFIX + ticket)
    finally:
        r.close()
    return json.loads(raw) if raw else None
