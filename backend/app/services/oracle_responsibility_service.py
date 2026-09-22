"""
Oracle EBS Responsibility Lookup (read-only)
─────────────────────────────────────────
Backs Setup > Access Center's third panel — a read-only cross-reference of
which Oracle EBS responsibilities a person's account currently holds,
queried as the app's existing shared APPS account (get_oracle_connection())
— no new Oracle credential needed, APPS already has full read access to
the FND_* security tables.

This does NOT manage Oracle EBS access in any way — Oracle's own
Responsibility model stays entirely under Oracle's own System Administrator
responsibility, unchanged by this app. It exists purely so an admin
answering "what can this person do" doesn't have to separately open Oracle
EBS to check; see ebs_chat_service.py's own docstring for why this app
otherwise stays out of Oracle's responsibility/security model entirely
(its org hierarchy carries no usable department info here).

Matched by FND_USER.EMAIL_ADDRESS = the caller's email — verified live
against real accounts: works cleanly for regular staff (their own named
Oracle account, e.g. "DESSY"), but for the 2-3 people who administer Oracle
EBS itself, EMAIL_ADDRESS on FND_USER is registered against a SHARED/GENERIC
account (SYSTEM, ITSUPPORT) rather than a personal one — those accounts
legitimately hold 100+ responsibilities because they're superuser/shared
logins, not because that one person personally has that much access.
_is_shared_account() flags this so the panel can show a clear warning
instead of presenting it as if it were personal.
"""
import asyncio

import structlog

from app.database import get_oracle_connection

logger = structlog.get_logger()

# Oracle usernames known to be shared/admin accounts rather than a single
# person's own login — verified live (SYSTEM holds mashudi@ckd-otto.com's
# registered email, ITSUPPORT holds utomo@ckd-otto.com's). Extend this list
# if another shared account turns up with a real person's email attached.
_SHARED_ACCOUNT_PATTERNS = ("SYSTEM", "ITSUPPORT", "ADMIN", "GUEST", "SYSADMIN")


def _is_shared_account(oracle_username: str) -> bool:
    return (oracle_username or "").upper() in _SHARED_ACCOUNT_PATTERNS


def _query(sql: str, params: dict) -> list[dict]:
    with get_oracle_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        columns = [col[0].lower() for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


_USER_SQL = """
    SELECT user_id, user_name, employee_id
      FROM fnd_user
     WHERE UPPER(email_address) = UPPER(:email)
"""

_RESP_SQL = """
    SELECT frt.responsibility_name, furgd.start_date, furgd.end_date
      FROM fnd_user fu, fnd_user_resp_groups_direct furgd, fnd_responsibility_tl frt
     WHERE fu.user_id = furgd.user_id
           AND furgd.responsibility_id = frt.responsibility_id
           AND furgd.responsibility_application_id = frt.application_id
           AND frt.language = 'US'
           AND (furgd.end_date IS NULL OR furgd.end_date > SYSDATE)
           AND fu.user_id = :user_id
     ORDER BY frt.responsibility_name
"""


async def get_responsibilities_for_email(email: str) -> dict:
    """Returns {"found": False} if no Oracle account is registered against
    this email at all (a real, common case — not every Dashboard user has
    Oracle EBS access), else {"found": True, "oracle_username": str,
    "is_shared_account": bool, "responsibilities": [{"name","since"}]}."""
    email = (email or "").strip().lower()
    if not email:
        return {"found": False}
    try:
        users = await asyncio.to_thread(_query, _USER_SQL, {"email": email})
        if not users:
            return {"found": False}
        user = users[0]
        resps = await asyncio.to_thread(_query, _RESP_SQL, {"user_id": user["user_id"]})
        return {
            "found": True,
            "oracle_username": user["user_name"],
            "is_shared_account": _is_shared_account(user["user_name"]),
            "responsibilities": [
                {"name": r["responsibility_name"], "since": r["start_date"].isoformat() if r["start_date"] else None}
                for r in resps
            ],
        }
    except Exception as e:
        logger.error("oracle_responsibility_lookup_error", email=email, error=str(e))
        return {"found": False, "error": str(e)}
