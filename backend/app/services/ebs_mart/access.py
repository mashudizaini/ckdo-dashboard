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

from app.services.ebs_mart.constants import BUILT_MARTS, DOMAIN_BY_GROUP, EBS_GROUPS


@dataclass
class Caller:
    email: str
    groups: set[str] = field(default_factory=set)
    source: str = ""          # "keycloak" | "service-key" | "dashboard"
    chat_id: str | None = None

    @property
    def prefixes(self) -> set[str]:
        out: set[str] = set()
        for g in self.groups:
            out |= DOMAIN_BY_GROUP.get(g, set())
        return out

    def can_read(self, mart: str) -> bool:
        return any(mart.startswith(p) for p in self.prefixes)

    def readable_marts(self) -> list[str]:
        return [m for m in BUILT_MARTS if self.can_read(m)]


def normalize_groups(raw) -> set[str]:
    """Keycloak's group-membership mapper emits full paths ("/ebs-finance")
    unless "Full group path" is switched off; accept both, keep only the
    groups this module knows."""
    out = set()
    for g in raw or []:
        name = str(g).strip().strip("/").split("/")[-1].lower()
        if name in DOMAIN_BY_GROUP:
            out.add(name)
    return out


def scope_groups(email: str) -> set[str]:
    """ebs_chat_scope.ebs_groups for this email (empty when unregistered)."""
    from app.services.ebs_chat_service import _get_pg

    conn = _get_pg()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT ebs_groups FROM ebs_chat_scope WHERE email = %s",
            ((email or "").strip().lower(),),
        )
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
    if not caller.can_read(mart):
        groups = ", ".join(sorted(caller.groups)) or "tidak ada"
        raise AccessDenied(
            f"Anda tidak punya akses ke mart.{mart}. Grup EBS Anda: {groups}. "
            f"Data ini di luar hak akses Anda — jangan mencari jalur lain."
        )


__all__ = ["Caller", "AccessDenied", "normalize_groups", "scope_groups", "require", "EBS_GROUPS"]
