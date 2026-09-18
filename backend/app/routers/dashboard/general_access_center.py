"""
Access Center Router
Route prefix : /api/v1/dashboard/general/access-center
Required role: admin (every endpoint here)

Endpoints:
  GET    /user/{email}          — combined view: Keycloak roles + Oracle EBS
                                   responsibilities (read-only) for one email
                                   (EBS Chat scope is its own existing CRUD
                                   at /ai/ebs-chat/scope — not duplicated here)
  GET    /keycloak/roles        — realm roles available to assign
  PUT    /keycloak/{email}/roles/{role_name}    — assign (needs
                                   keycloak_admin_service configured)
  DELETE /keycloak/{email}/roles/{role_name}    — revoke
"""
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import CurrentUser, Roles, require_role
from app.services import keycloak_admin_service, oracle_responsibility_service

router = APIRouter()


def _require_keycloak_admin_configured():
    if not keycloak_admin_service.is_configured():
        raise HTTPException(503, "Keycloak Admin API belum dikonfigurasi (KEYCLOAK_ADMIN_CLIENT_ID/SECRET belum diset)")


@router.get("/keycloak/roles")
async def get_keycloak_roles(user: CurrentUser = Depends(require_role(Roles.ADMIN))):
    _require_keycloak_admin_configured()
    return await keycloak_admin_service.list_realm_roles()


@router.get("/user/{email}")
async def get_user_access(email: str, user: CurrentUser = Depends(require_role(Roles.ADMIN))):
    keycloak_result = {"configured": keycloak_admin_service.is_configured(), "found": False, "roles": []}
    if keycloak_result["configured"]:
        kc_user = await keycloak_admin_service.find_user_by_email(email)
        if kc_user:
            keycloak_result["found"] = True
            keycloak_result["user_id"] = kc_user["id"]
            keycloak_result["roles"] = await keycloak_admin_service.get_user_roles(kc_user["id"])

    oracle_result = await oracle_responsibility_service.get_responsibilities_for_email(email)

    return {"email": email.strip().lower(), "keycloak": keycloak_result, "oracle": oracle_result}


@router.put("/keycloak/{email}/roles/{role_name}")
async def assign_keycloak_role(email: str, role_name: str, user: CurrentUser = Depends(require_role(Roles.ADMIN))):
    _require_keycloak_admin_configured()
    kc_user = await keycloak_admin_service.find_user_by_email(email)
    if not kc_user:
        raise HTTPException(404, f"No Keycloak user found for {email}")
    await keycloak_admin_service.assign_role(kc_user["id"], role_name)
    return {"success": True}


@router.delete("/keycloak/{email}/roles/{role_name}")
async def revoke_keycloak_role(email: str, role_name: str, user: CurrentUser = Depends(require_role(Roles.ADMIN))):
    _require_keycloak_admin_configured()
    kc_user = await keycloak_admin_service.find_user_by_email(email)
    if not kc_user:
        raise HTTPException(404, f"No Keycloak user found for {email}")
    await keycloak_admin_service.revoke_role(kc_user["id"], role_name)
    return {"success": True}
