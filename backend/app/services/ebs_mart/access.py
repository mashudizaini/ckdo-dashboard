"""
Who may read which mart (blueprint section 7, "Row-level security per domain").

A caller's effective ebs-* groups are the union of two sources:
  - the `groups` claim of their Keycloak token, when Open WebUI forwards the
    user's OAuth token to the tool server (the blueprint's preferred path);
  - ebs_chat_scope.ebs_groups for their email, set in Setup > AI > EBS Chat
    Access — for the service-key path, and for anyone whose Keycloak account
    does not carry the groups yet.

Union rather than one overriding the other: both are grants made by an
administrator, and neither is a denial list. A caller with no ebs-* group at
all reads nothing — there is no default grant, unlike allowed_modules in
ebs_chat_service where an empty list predates the column and means
"unrestricted".
"""
from dataclasses import dataclass, field

from app.services.ebs_mart.constants import BUILT_MARTS, DOMAIN_BY_GROUP, EBS_GROUPS, SA_PREFIX, SYSADMIN_ALLOWLIST


@dataclass
class Caller:
    email: str
    groups: set[str] = field(default_factory=set)
    source: str = ""          # "keycloak" | "service-key" | "dashboard"
    chat_id: str | None = None

    @property
    def levels(self) -> dict[str, str]:
        """mart -> "full" | "qty" from the access policy (policy.py) for this
        caller's roles; computed once per caller."""
        cached = self.__dict__.get("_levels")
        if cached is None:
            from app.services.ebs_mart import policy
            cached = policy.levels_for(self.groups)
            self.__dict__["_levels"] = cached
        return cached

    def level(self, mart: str) -> str | None:
        if mart.startswith(SA_PREFIX):
            return "full" if self.is_sysadmin else None
        return self.levels.get(mart)

    @property
    def is_sysadmin(self) -> bool:
        return (self.email or "").strip().lower() in SYSADMIN_ALLOWLIST

    def can_read(self, mart: str) -> bool:
        # System Administration marts follow the email allowlist only — no
        # group reaches them, not even ebs-management's "" prefix.
        if mart.startswith(SA_PREFIX):
            return self.is_sysadmin
        return mart in self.levels

    def readable_marts(self) -> list[str]:
        return [m for m in BUILT_MARTS if self.can_read(m)]


def normalize_groups(raw) -> set[str]:
    """Keycloak's group-membership mapper emits full paths ("/ebs-finance")
    unless "Full group path" is switched off; accept both, keep only the
    access roles the policy knows (meta.access_role)."""
    from app.services.ebs_mart import policy
    known = set(policy.role_codes())
    out = set()
    for g in raw or []:
        name = str(g).strip().strip("/").split("/")[-1].lower()
        if name in known:
            out.add(name)
    return out


def scope_groups(email: str) -> set[str]:
    """ebs_chat_scope.ebs_groups for this email. A known employee with no row
    yet gets the department/team default first (ebs_chat_defaults.py), same
    as EBS Assistant; empty when the email is not an active employee."""
    from app.services.ebs_chat_service import _get_pg
    from app.services.ebs_chat_defaults import provision_default_scope

    email = (email or "").strip().lower()
    conn = _get_pg()
    try:
        cur = conn.cursor()
        cur.execute("SELECT ebs_groups FROM ebs_chat_scope WHERE email = %s", (email,))
        row = cur.fetchone()
        if not row and provision_default_scope(conn, email):
            cur = conn.cursor()
            cur.execute("SELECT ebs_groups FROM ebs_chat_scope WHERE email = %s", (email,))
            row = cur.fetchone()
        return normalize_groups(row[0] if row else [])
    except Exception:
        # Column not migrated yet on this host — treat as no grant.
        return set()
    finally:
        conn.close()


class AccessDenied(PermissionError):
    pass


def require(caller: Caller, mart: str):
    if mart.startswith(SA_PREFIX) and not caller.is_sysadmin:
        raise AccessDenied("Data System Administration hanya untuk tim IT tertentu "
                           f"(allowlist email). {caller.email or 'User ini'} tidak termasuk — jangan mencari jalur lain.")
    if not caller.can_read(mart):
        groups = ", ".join(sorted(caller.groups)) or "tidak ada"
        raise AccessDenied(
            f"Anda tidak punya akses ke mart.{mart}. Grup EBS Anda: {groups}. "
            f"Data ini di luar hak akses Anda — jangan mencari jalur lain."
        )


__all__ = ["Caller", "AccessDenied", "normalize_groups", "scope_groups", "require", "EBS_GROUPS"]
