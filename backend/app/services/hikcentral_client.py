"""
HikCentral OpenAPI (Artemis) client — pulls raw access-control events from
the office's Hikvision DS-K1T342MFWX face-recognition terminals, aggregated
behind the HikCentral server the terminals already report to (screenshot:
"HikCentral Access Control" web client at https://<host>/#/portal).

We deliberately pull RAW check-in events, not HikCentral's own computed
Present/Absent/Leave numbers (visible in its "Attendance Report" widget) —
those get normalized into AttendanceRecord and scored by this app's own
_plan_expr()/_actual_expr() rules (see hr_attendance.py's module docstring),
the same as every other source (Intercom/Talenta/Plant/Office). Importing
HikCentral's own computed rate instead would create two different attendance
methodologies that could silently disagree.

── SIGNING — NEEDS VERIFICATION AGAINST YOUR HIKCENTRAL EDITION ──
The scheme below (HMAC-SHA256 over a canonical string, Alibaba Cloud API
Gateway-style headers) is Hikvision's documented Artemis/OpenAPI signing
convention and is consistent across most HikCentral Professional/Enterprise
deployments, but exact header casing/order can vary by version. Before
relying on this in production:
  1. In HikCentral: System > Open Platform (or "Third-party Integration") >
     add an application to get an AppKey + AppSecret.
  2. Most HikCentral installs ship (or let you download) an "OpenAPI
     Development Guide" PDF and/or a Postman collection with one WORKED
     signed-request example for your exact version — use that to confirm
     the canonical-string format matches `_build_headers()` below, and fix
     it here if not (that's the only function that should need to change).
  3. The endpoint path in `search_door_events()` (/artemis/api/acs/v1/door/
     events) is Hikvision's standard ACS event-search endpoint, stable
     across editions — but if your HikCentral build exposes a dedicated
     Attendance-module raw-record endpoint, that may be a better fit and
     can replace this call without touching anything else in this file.
"""
import base64
import hashlib
import hmac
import json
import time
from typing import Optional

import httpx

from app.config import get_settings


class HikCentralError(Exception):
    pass


def _build_headers(app_key: str, app_secret: str, method: str, path: str, body_str: str) -> dict:
    """Builds the signed request headers. HMAC-SHA256 over a canonical
    string (method/Accept/Content-MD5/Content-Type/Date/signed-headers/
    path) — Content-MD5 and Date are left blank since the body isn't
    MD5-hashed and X-Ca-Timestamp is used instead of the Date header."""
    accept = "application/json"
    content_type = "application/json;charset=UTF-8" if body_str else ""
    timestamp = str(int(time.time() * 1000))

    string_to_sign = (
        f"{method}\n"
        f"{accept}\n"
        "\n"
        f"{content_type}\n"
        "\n"
        f"x-ca-key:{app_key}\n"
        f"x-ca-timestamp:{timestamp}\n"
        f"{path}"
    )
    digest = hmac.new(app_secret.encode(), string_to_sign.encode(), hashlib.sha256).digest()
    signature = base64.b64encode(digest).decode()

    headers = {
        "Accept": accept,
        "x-ca-key": app_key,
        "x-ca-timestamp": timestamp,
        "x-ca-signature-headers": "x-ca-key,x-ca-timestamp",
        "x-ca-signature": signature,
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


class HikCentralClient:
    def __init__(self, base_url: Optional[str] = None, app_key: Optional[str] = None, app_secret: Optional[str] = None):
        s = get_settings()
        self.base_url = (base_url or s.hikcentral_base_url).rstrip("/")
        self.app_key = app_key or s.hikcentral_app_key
        self.app_secret = app_secret or s.hikcentral_app_secret
        if not (self.base_url and self.app_key and self.app_secret):
            raise HikCentralError(
                "HikCentral not configured — set hikcentral_base_url / "
                "hikcentral_app_key / hikcentral_app_secret (.env)"
            )

    def _post(self, path: str, payload: dict) -> dict:
        body_str = json.dumps(payload)
        headers = _build_headers(self.app_key, self.app_secret, "POST", path, body_str)
        url = f"{self.base_url}{path}"
        with httpx.Client(verify=False, timeout=30) as client:  # HikCentral's local cert is usually self-signed
            resp = client.post(url, content=body_str, headers=headers)
        try:
            data = resp.json()
        except Exception as exc:
            raise HikCentralError(f"HikCentral returned non-JSON (HTTP {resp.status_code}): {resp.text[:300]}") from exc
        if data.get("code") not in ("0", 0, None):
            raise HikCentralError(f"HikCentral API error {data.get('code')}: {data.get('msg')}")
        return data.get("data", data)

    def search_door_events(self, start_time: str, end_time: str, page_no: int = 1, page_size: int = 1000) -> dict:
        """Raw ACS (access control) events in [start_time, end_time)
        (ISO-8601, e.g. "2026-08-13T00:00:00+07:00") — each face-recognition
        pass at a terminal is one event, carrying personId/name/time/
        doorName. This is the "raw check-in/out" data source; pagination via
        pageNo/pageSize (HikCentral typically caps pageSize around 1000)."""
        return self._post("/artemis/api/acs/v1/door/events", {
            "startTime": start_time,
            "endTime": end_time,
            "pageNo": page_no,
            "pageSize": page_size,
        })
