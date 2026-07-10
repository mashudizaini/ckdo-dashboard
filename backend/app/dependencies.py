from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from app.config import get_settings
import httpx
import structlog
import time

logger = structlog.get_logger()
settings = get_settings()

security = HTTPBearer()

_jwks_cache: dict = {}
_jwks_fetched_at: float = 0.0
_JWKS_TTL_SECONDS = 600  # re-fetch periodically so a Keycloak key rotation self-heals


async def get_jwks(force: bool = False) -> dict:
    """Fetch JWKS from Keycloak — cached in memory with a TTL.

    Without a TTL, a cached-forever JWKS would permanently fail to validate
    any token if Keycloak's signing keys ever rotate (realm re-import,
    manual key regeneration, etc.) until this backend process restarts —
    every request would 401 with "Invalid or expired token" even for a
    token that is, in fact, perfectly fresh.
    """
    global _jwks_cache, _jwks_fetched_at
    now = time.monotonic()
    if _jwks_cache and not force and (now - _jwks_fetched_at) < _JWKS_TTL_SECONDS:
        return _jwks_cache
    jwks_url = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/certs"
    async with httpx.AsyncClient() as client:
        response = await client.get(jwks_url, timeout=10)
        response.raise_for_status()
        _jwks_cache = response.json()
        _jwks_fetched_at = now
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
        try:
            token_data = jwt.decode(
                token, jwks, algorithms=["RS256"], options={"verify_aud": False},
            )
        except JWTError:
            # Cached JWKS may be stale (e.g. right after a Keycloak restart) —
            # force one re-fetch and retry before concluding the token itself
            # is bad. Avoids every request 401ing until this process restarts.
            jwks = await get_jwks(force=True)
            token_data = jwt.decode(
                token, jwks, algorithms=["RS256"], options={"verify_aud": False},
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
