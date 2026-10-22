"""
One place to build Anthropic SDK clients.

Every Claude call in the backend goes through anthropic_client() so the
company key's workspace (settings.anthropic_workspace_id, from
ANTHROPIC_WORKSPACE_ID in .env) is sent as the anthropic-workspace-id
header. An organisation-level key that isn't scoped to a workspace is
rejected without it: "This API key is not scoped to a workspace, so this
request must include the anthropic-workspace-id header".

The header is only added for the company key. A user's own key (user API
keys, per-user provider settings) belongs to whoever created it and may
sit in a different workspace or organisation, so it is passed through
as-is.
"""
from typing import Optional

import anthropic

from app.config import get_settings


def anthropic_client(api_key: Optional[str] = None, *, async_: bool = False):
    """anthropic.Anthropic (or AsyncAnthropic with async_=True) for
    `api_key`, falling back to the company key when it's empty."""
    settings = get_settings()
    key = api_key or settings.anthropic_api_key
    cls = anthropic.AsyncAnthropic if async_ else anthropic.Anthropic
    workspace = (settings.anthropic_workspace_id or "").strip()
    if workspace and key == settings.anthropic_api_key:
        return cls(api_key=key, default_headers={"anthropic-workspace-id": workspace})
    return cls(api_key=key)
