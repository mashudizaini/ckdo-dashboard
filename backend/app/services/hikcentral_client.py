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

── Digest auth: manual nonce reuse (root-caused 2026-08-27) ──
httpx's built-in `httpx.DigestAuth` re-does the FULL challenge/response
handshake on every single request: it sends the request with no
credentials, gets a 401 with a fresh nonce, then resends with the computed
digest — two round trips per call, every call. At real backfill volume
(thousands of sequential requests) this device's firmware apparently counts
every one of those "probe" 401s toward its own brute-force/illegal-login
lockout counter, even though the overall exchange always ends in success —
confirmed live: a 5-day backfill using httpx.DigestAuth failed all 5 days
with a locked-out `<userCheck>` 401 response.

Fix: cache the digest challenge (realm/nonce/qop/opaque) from the first
401 and reuse it for subsequent requests, incrementing `nc` and generating
a fresh `cnonce` each time per RFC 7616 — most requests then never trigger
a 401 at all. Falls back to re-challenging if the device rejects a reused
nonce (it does expire it periodically). Verified live: an 80-request
rapid-fire burst with nonce reuse completed with 0 failures (vs. entire
backfill days failing under the old per-request-challenge approach).
"""
import hashlib
import re
import time
from typing import Optional

import httpx

from app.config import get_settings


class HikCentralError(Exception):
    pass


class _CachedDigestAuth:
    """Manual HTTP Digest Auth (RFC 7616) with nonce reuse across requests
    on the same client — see module docstring for why this replaces
    httpx.DigestAuth. Not thread-safe; one instance per HikCentralClient,
    used sequentially (this integration's scheduler/backfill never issue
    concurrent requests through the same client)."""

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self._challenge: Optional[dict] = None
        self._nc = 0

    @staticmethod
    def _parse_challenge(header: str) -> dict:
        parts = {}
        for m in re.finditer(r'(\w+)=(?:"([^"]*)"|([^\s,]+))', header):
            parts[m.group(1)] = m.group(2) if m.group(2) is not None else m.group(3)
        return parts

    def _auth_header(self, method: str, path: str) -> str:
        ch = self._challenge
        self._nc += 1
        nc = f"{self._nc:08x}"
        cnonce = hashlib.sha1(f"{time.time()}{self._nc}{path}".encode()).hexdigest()[:16]
        ha1 = hashlib.md5(f"{self.username}:{ch['realm']}:{self.password}".encode()).hexdigest()
        ha2 = hashlib.md5(f"{method}:{path}".encode()).hexdigest()
        qop = ch.get("qop", "auth").split(",")[0].strip()
        response = hashlib.md5(f"{ha1}:{ch['nonce']}:{nc}:{cnonce}:{qop}:{ha2}".encode()).hexdigest()
        header = (
            f'Digest username="{self.username}", realm="{ch["realm"]}", '
            f'nonce="{ch["nonce"]}", uri="{path}", response="{response}", '
            f'qop={qop}, nc={nc}, cnonce="{cnonce}"'
        )
        if ch.get("opaque"):
            header += f', opaque="{ch["opaque"]}"'
        if ch.get("algorithm"):
            header += f', algorithm={ch["algorithm"]}'
        return header

    def request(self, client: httpx.Client, method: str, url: str, **kwargs) -> httpx.Response:
        path = httpx.URL(url).raw_path.decode()
        if self._challenge is not None:
            headers = dict(kwargs.pop("headers", None) or {})
            headers["Authorization"] = self._auth_header(method, path)
            resp = client.request(method, url, headers=headers, **kwargs)
            if resp.status_code != 401:
                return resp
            # Cached nonce rejected (expired/stale) — re-challenge below.
        resp = client.request(method, url, **kwargs)
        if resp.status_code == 401 and "WWW-Authenticate" in resp.headers:
            self._challenge = self._parse_challenge(resp.headers["WWW-Authenticate"])
            self._nc = 0
            headers = dict(kwargs.pop("headers", None) or {})
            headers["Authorization"] = self._auth_header(method, path)
            resp = client.request(method, url, headers=headers, **kwargs)
        return resp


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
        self._client = httpx.Client(timeout=30)
        self._auth = _CachedDigestAuth(self.username, self.password)

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
                resp = self._auth.request(self._client, "POST", url, json=payload)
            except httpx.HTTPError as exc:
                raise HikCentralError(f"Could not reach Hikvision device at {self.base_url}: {exc}") from exc
            if resp.status_code == 401 and attempt < max_attempts - 1:
                # Genuine lockout (rare now that requests aren't each
                # starting with an unauthenticated probe) — back off and
                # retry rather than failing this request outright.
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
