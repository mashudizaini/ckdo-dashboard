from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from app.config import get_settings
import httpx
import structlog

logger = structlog.get_logger()
settings = get_settings()

security = HTTPBearer()

_jwks_cache: dict = {}

async def get_jwks() -> dict:
    """Fetch JWKS from Keycloak — cached in memory."""
    if _jwks_cache:
        return _jwks_cache
    jwks_url = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/certs"
    async with httpx.AsyncClient() as client:
        response = await client.get(jwks_url, timeout=10)
        response.raise_for_status()
        _jwks_cache.update(response.json())
    return _jwks_cache


# ─────────────────────────────────────────
# USER INFO MODEL (from Keycloak token)
# ─────────────────────────────────────────

class CurrentUser:
    def __init__(self, token_data: dict):
        self.id: str = token_data.get("sub", "")
        self.username: str = token_data.get("preferred_username", "")
        self.email: str = token_data.get("email", "")
        self.full_name: str = token_data.get("name", "")
        # Keycloak realm roles
        realm_access = token_data.get("realm_access", {})
        self.roles: list[str] = realm_access.get("roles", [])

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def has_any_role(self, *roles: str) -> bool:
        return any(r in self.roles for r in roles)


# ─────────────────────────────────────────
# DEPENDENCIES
# ─────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> CurrentUser:
    """
    FastAPI dependency — validates Keycloak Bearer token via JWKS.
    Injects CurrentUser into route handlers.
    """
    token = credentials.credentials
    try:
        jwks = await get_jwks()
        token_data = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        return CurrentUser(token_data)
    except JWTError as e:
        logger.warning("Token validation failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.warning("Token validation failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_role(*roles: str):
    """
    FastAPI dependency factory — enforces role-based access.

    Usage:
        @router.get("/it/data", dependencies=[Depends(require_role("it_staff", "admin"))])
    """
    async def role_checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not user.has_any_role(*roles, "admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {list(roles)}",
            )
        return user
    return role_checker


# ─────────────────────────────────────────
# ROLE CONSTANTS — gunakan ini di router
# ─────────────────────────────────────────

class Roles:
    ADMIN = "admin"
    IT = "it_staff"
    HR = "hr_staff"
    PAC = "pac_staff"
    ACCOUNTING = "accounting_staff"
    PURCHASING = "purchasing_staff"
