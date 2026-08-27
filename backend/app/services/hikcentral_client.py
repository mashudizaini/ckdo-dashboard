"""
Hikvision ISAPI client — pulls raw access-control (face/card authentication)
events directly from the office's Hikvision DS-K1T342MFWX terminal at its
own IP (HTTP digest auth, e.g. http://192.168.1.20), rather than through a
HikCentral aggregation server. This app talks to the terminal itself.

We deliberately pull RAW events, not any device-side computed attendance
status — normalized into AttendanceRecord by this app's own
_plan_expr()/_actual_expr() rules (see hr_attendance.py's module docstring),
same as every other source (Intercom/Talenta/Plant/Office).

── Confirmed live against the real device ──
  - Every JSON POST must have `?format=json` appended to the URL itself —
    the device parses XML vs JSON based on this query param, not the
    Content-Type header or actual body content.
  - `AcsEventCond.maxResults` is capped at 30 by this device's firmware
    (see GET /ISAPI/AccessControl/AcsEvent/capabilities?format=json).
    Pagination is via `searchResultPosition`, not a real page size.
  - Only events carrying `employeeNoString` are an actual face/card
    authentication pass identifying a person (major=5/minor=75 on this
    device); door-open/close and periodic heartbeat events (e.g.
    major=5/minor=21/22, major=3/minor=1029) don't carry identity and are
    filtered out by the caller.
  - Event fields used: employeeNoString (matches Employee.user_id and the
    roster's employeeNo — confirmed e.g. "A25002"), name, time (ISO-8601
    with timezone offset, e.g. "2026-08-26T07:14:12+07:00").
  - The client is a persistent httpx.Client (reused across calls, close()d
    by the caller when done) rather than one-per-request — a historical
    backfill fires thousands of sequential requests, and each fresh
    httpx.Client + DigestAuth pair used to mean a brand-new TCP connection
    AND a full unauthenticated-probe/401-challenge/authenticated-retry
    round trip every single time. Under that load this firmware's
    brute-force/"illegal login" lockout occasionally trips — even though
    every individual request eventually succeeds — and briefly returns an
    XML `<userCheck>` 401 body instead of the requested JSON (confirmed
    live during a real backfill run, ~2 of ~230 days). `_post_json()`
    retries with backoff on a 401 to ride out that window instead of
    failing the whole day.
"""
import time
from typing import Optional

import httpx

from app.config import get_settings


class HikCentralError(Exception):
    pass


class HikCentralClient:
    def __init__(self, base_url: Optional[str] = None, username: Optional[str] = None, password: Optional[str] = None):
        s = get_settings()
        self.base_url = (base_url or s.hikcentral_base_url).rstrip("/")
        self.username = username or s.hikcentral_app_key
        self.password = password or s.hikcentral_app_secret
        if not (self.base_url and self.username and self.password):
            raise HikCentralError(
                "Hikvision device not configured — set hikcentral_base_url / "
                "hikcentral_app_key / hikcentral_app_secret (.env), or fill in "
                "IT Dashboard > HikCentral Integration (device host / username / password)"
            )
        self._client = httpx.Client(auth=httpx.DigestAuth(self.username, self.password), timeout=30)

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def _post_json(self, path: str, payload: dict, max_attempts: int = 4) -> dict:
        url = f"{self.base_url}{path}?format=json"
        resp = None
        for attempt in range(max_attempts):
            try:
                resp = self._client.post(url, json=payload)
            except httpx.HTTPError as exc:
                raise HikCentralError(f"Could not reach Hikvision device at {self.base_url}: {exc}") from exc
            if resp.status_code == 401 and attempt < max_attempts - 1:
                # Transient device-side lockout (see module docstring) —
                # back off and retry rather than failing this request.
                time.sleep(2 * (attempt + 1))
                continue
            break
        try:
            data = resp.json()
        except Exception as exc:
            raise HikCentralError(f"Device returned non-JSON (HTTP {resp.status_code}): {resp.text[:300]}") from exc
        if resp.status_code != 200:
            detail = data.get("subStatusCode") or data.get("statusString") or data.get("errorMsg") or data
            raise HikCentralError(f"Device error (HTTP {resp.status_code}): {detail}")
        return data

    def search_door_events(self, start_time: str, end_time: str, search_position: int = 0, max_results: int = 30) -> dict:
        """Raw access-control events in [start_time, end_time) (ISO-8601
        with tz offset, e.g. "2026-08-26T00:00:00+07:00"). max_results is
        capped at 30 by this device's firmware regardless of what's
        requested; paginate via search_position, following
        responseStatusStrg == "MORE", until it isn't."""
        data = self._post_json("/ISAPI/AccessControl/AcsEvent", {
            "AcsEventCond": {
                "searchID": "1",
                "searchResultPosition": search_position,
                "maxResults": min(max_results, 30),
                "major": 0,
                "minor": 0,
                "startTime": start_time,
                "endTime": end_time,
                "picEnable": False,
            }
        })
        block = data.get("AcsEvent")
        if block is None:
            raise HikCentralError(f"Unexpected device response: {data}")
        return {
            "list": block.get("InfoList", []),
            "totalMatches": block.get("totalMatches", 0),
            "responseStatusStrg": block.get("responseStatusStrg"),
        }
