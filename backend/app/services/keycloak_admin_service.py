"""
Keycloak Admin Service
─────────────────────────────────────────
Thin wrapper around Keycloak's Admin REST API, authenticated as the
`ckdo-dashboard-admin` service account (a separate confidential client from
`keycloak_client_id`, which is the frontend's public login client and has
no admin privileges at all). Backs Setup > Access Center's Dashboard-role
panel — list/assign/revoke realm roles for a user, from inside this app
instead of needing the separate Keycloak Admin Console for every grant.

Scoped deliberately narrow: the service account only holds view-realm/
view-users/manage-users/query-users (realm-management client roles) — not
manage-realm, manage-clients, or anything else. It can look at and edit
role MEMBERSHIP, nothing about how the realm/clients themselves are
configured.

A role change made here doesn't take effect for an already-logged-in user
until their next token refresh/re-login — same as any Keycloak role change
made through the Admin Console, not a limitation specific to this service.
"""
from typing import Optional

import httpx
import structlog

from app.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


def _base_url() -> str:
    return settings.keycloak_url.rstrip("/")


def is_configured() -> bool:
    return bool(settings.keycloak_admin_client_id and settings.keycloak_admin_client_secret)


async def _get_token() -> str:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{_base_url()}/realms/{settings.keycloak_realm}/protocol/openid-connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": settings.keycloak_admin_client_id,
                "client_secret": settings.keycloak_admin_client_secret,
            },
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


async def _admin_request(method: str, path: str, **kwargs) -> httpx.Response:
    token = await _get_token()
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.request(
            method, f"{_base_url()}/admin/realms/{settings.keycloak_realm}{path}",
            headers={"Authorization": f"Bearer {token}"}, **kwargs,
        )
        resp.raise_for_status()
        return resp


async def list_realm_roles() -> list[dict]:
    """All realm roles, excluding Keycloak's own default/technical ones —
    those aren't meaningful "Dashboard access" grants to show an admin."""
    resp = await _admin_request("GET", "/roles")
    hidden = {"default-roles-ckdo", "offline_access", "uma_authorization"}
    return [
        {"name": r["name"], "description": r.get("description") or ""}
        for r in resp.json() if r["name"] not in hidden
    ]


async def find_user_by_email(email: str) -> Optional[dict]:
    resp = await _admin_request("GET", "/users", params={"email": email.strip().lower(), "exact": "true"})
    users = resp.json()
    return users[0] if users else None


async def get_user_roles(user_id: str) -> list[str]:
    resp = await _admin_request("GET", f"/users/{user_id}/role-mappings/realm")
    return sorted(r["name"] for r in resp.json())


async def assign_role(user_id: str, role_name: str) -> None:
    role_resp = await _admin_request("GET", f"/roles/{role_name}")
    role = role_resp.json()
    await _admin_request(
        "POST", f"/users/{user_id}/role-mappings/realm",
        json=[{"id": role["id"], "name": role["name"]}],
    )


async def revoke_role(user_id: str, role_name: str) -> None:
    role_resp = await _admin_request("GET", f"/roles/{role_name}")
    role = role_resp.json()
    await _admin_request(
        "DELETE", f"/users/{user_id}/role-mappings/realm",
        json=[{"id": role["id"], "name": role["name"]}],
    )
