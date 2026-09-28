"""
Data access policy for EBS chat: which access role may read which mart, and
how much of it — edited in Setup > AI > EBS Chat Access, stored in meta.

  meta.access_role   a role (ebs-finance, ebs-purchasing, ... or any role an
                     admin adds). all_access = every mart except sa_* (the
                     management role), so new marts need no new grant.
  meta.access_grant  role × mart × level:
                       full — every column
                       qty  — quantities, dates and names only: columns that
                              carry money (amounts, prices, costs, values) are
                              removed from every result, and run_sql may not
                              reference them (see query.run / tools.run_sql)

A user's roles come from ebs_chat_scope.ebs_groups (and the Keycloak token's
groups/roles with the same names). Grants from several roles add up; full
wins over qty. System Administration marts (sa_*) are outside this policy
altogether — the email allowlist decides (access.py).

On first start the tables are seeded from the mapping that used to be code
(constants.DOMAIN_BY_GROUP), so behaviour does not change on deploy, plus
two quantity-only grants that mapping could not express: purchasing sees
stock on hand and stock movements (what is in the warehouse before
ordering), warehouse sees open PO lines (what is arriving and when) —
neither sees a price or a value.
"""
import re
import time

from app.services.ebs_mart.constants import DOMAIN_BY_GROUP, GROUP_LABELS, MARTS, SA_PREFIX

LEVELS = ("full", "qty")

POLICY_DDL = [
    """
    CREATE TABLE IF NOT EXISTS meta.access_role (
        role_code   text PRIMARY KEY,
        label       text NOT NULL,
        description text,
        all_access  boolean NOT NULL DEFAULT false,
        updated_by  text,
        updated_at  timestamptz DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS meta.access_grant (
        role_code  text REFERENCES meta.access_role (role_code) ON DELETE CASCADE ON UPDATE CASCADE,
        mart_name  text,
        level      text NOT NULL CHECK (level IN ('full', 'qty')),
        updated_by text,
        updated_at timestamptz DEFAULT now(),
        PRIMARY KEY (role_code, mart_name)
    )
    """,
]

# Quantity-only defaults added on first seed (see module docstring).
_SEED_QTY = {
    "ebs-purchasing": ["inv_onhand_lot", "inv_movement_daily"],
    "ebs-warehouse": ["po_outstanding"],
}

# Column names that carry money. Matched against result columns (intent
# tools alias their sums with these endings) and against the columns run_sql
# references.
MONEY_COLUMN = re.compile(
    r"(_idr$|_idr_|_entered$|^amount|_amount|amount_|price|cost|value|^nbv$|nbv_|budget|encumbrance|"
    r"akumulasi|penyusutan|paid_|salary|gaji|^debit|^kredit|^credit|^saldo|balance|^selisih|^mutasi)",
    re.I,
)


def is_money(column: str) -> bool:
    return bool(MONEY_COLUMN.search(column or ""))


def _mart_names() -> list[str]:
    return [m for m, v in MARTS.items() if v.get("built") and not m.startswith(SA_PREFIX)]


def seed_policy(cur):
    """First start only: roles and grants from the old code mapping."""
    cur.execute("SELECT COUNT(*) FROM meta.access_role")
    if cur.fetchone()[0]:
        return
    marts = _mart_names()
    for role, prefixes in DOMAIN_BY_GROUP.items():
        all_access = "" in prefixes
        cur.execute(
            "INSERT INTO meta.access_role (role_code, label, all_access, updated_by) VALUES (%s, %s, %s, 'seed')",
            (role, GROUP_LABELS.get(role, role), all_access),
        )
        if all_access:
            continue
        for m in marts:
            if any(m.startswith(p) for p in prefixes):
                cur.execute(
                    "INSERT INTO meta.access_grant (role_code, mart_name, level, updated_by) VALUES (%s, %s, 'full', 'seed')",
                    (role, m),
                )
    for role, extra in _SEED_QTY.items():
        for m in extra:
            cur.execute(
                """INSERT INTO meta.access_grant (role_code, mart_name, level, updated_by) VALUES (%s, %s, 'qty', 'seed')
                   ON CONFLICT (role_code, mart_name) DO NOTHING""",
                (role, m),
            )


# ── Cached read ──────────────────────────────────────────────────────────────

_TTL = 30
_cache: dict = {"at": 0.0, "policy": None}


def invalidate():
    _cache["at"] = 0.0


def load() -> dict:
    """{"roles": {code: {"label", "description", "all_access"}},
        "grants": {code: {mart: level}}} — cached 30 s, invalidated on edit."""
    if _cache["policy"] is not None and time.monotonic() - _cache["at"] < _TTL:
        return _cache["policy"]
    from app.services.ebs_mart.query import _rw
    roles, grants = {}, {}
    conn = _rw()
    try:
        with conn.cursor() as cur:
            try:
                cur.execute("SELECT role_code, label, description, all_access FROM meta.access_role")
                for code, label, desc, all_access in cur.fetchall():
                    roles[code] = {"label": label, "description": desc, "all_access": all_access}
                    grants[code] = {}
                cur.execute("SELECT role_code, mart_name, level FROM meta.access_grant")
                for code, mart, level in cur.fetchall():
                    grants.setdefault(code, {})[mart] = level
            except Exception:
                conn.rollback()
                # Tables not created yet on this host: fall back to the seed
                # mapping so the tool server keeps working.
                marts = _mart_names()
                for role, prefixes in DOMAIN_BY_GROUP.items():
                    roles[role] = {"label": GROUP_LABELS.get(role, role), "description": None,
                                   "all_access": "" in prefixes}
                    grants[role] = {m: "full" for m in marts if "" not in prefixes
                                    and any(m.startswith(p) for p in prefixes)}
    finally:
        conn.close()
    policy = {"roles": roles, "grants": grants}
    _cache.update(at=time.monotonic(), policy=policy)
    return policy


def levels_for(roles: set[str]) -> dict[str, str]:
    """mart -> level for a set of roles; full beats qty. sa_* never appears."""
    p = load()
    out: dict[str, str] = {}
    for r in roles:
        if r not in p["roles"]:
            continue
        if p["roles"][r]["all_access"]:
            for m in _mart_names():
                out[m] = "full"
            continue
        for m, level in p["grants"].get(r, {}).items():
            if m.startswith(SA_PREFIX) or m not in MARTS:
                continue
            if out.get(m) != "full":
                out[m] = level
    return out


def role_codes() -> list[str]:
    return sorted(load()["roles"])
