"""
Oracle Environment Toggle
Route prefix: /api/v1/dashboard/general/oracle-env

Lets any authenticated user switch which Oracle instance the whole backend
is pointed at — Production or Development (see app/database.py's
get_oracle_environment()/set_oracle_environment()). One shared flag, not
per-user: the backend's Oracle connection is a single resource, so a
switch here applies to every user's next Oracle-backed request across the
whole app.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.database import get_oracle_environment, set_oracle_environment
from app.config import get_settings

router = APIRouter()
settings = get_settings()


class SetEnvRequest(BaseModel):
    environment: str  # "production" | "development"
    updated_by: str = "unknown"


@router.get("")
async def read_env():
    state = get_oracle_environment()
    state["prod_label"] = f"{settings.oracle_prod_host}:{settings.oracle_prod_port}/{settings.oracle_prod_service}"
    state["dev_label"] = f"{settings.oracle_dev_host}:{settings.oracle_dev_port}/{settings.oracle_dev_service}"
    return state


@router.put("")
async def write_env(body: SetEnvRequest):
    if body.environment not in ("production", "development"):
        raise HTTPException(status_code=400, detail="environment must be 'production' or 'development'")
    return set_oracle_environment(body.environment, body.updated_by)
