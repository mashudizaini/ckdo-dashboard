"""
ZKTeco protocol client — pulls the user roster + raw attendance log directly
from a Plant terminal (e.g. "Solution" X606-S, port 4370) over the standard
ZKTeco binary protocol, via the `pyzk` library (MIT, widely used against
ZKTeco and ZKTeco-compatible clone hardware).

── Confirmed live against the real device (Office terminal, 172.21.10.205,
   2026-08-28, via `docker exec` into the backend container since this
   dev workstation has no route to the Plant network but the deployed
   server does) ──
  - Firmware "Ver 6.60 Sep 19 2019", device name "X606-S", platform
    "ZMM220_TFT" — a genuine ZKTeco-family unit, not just protocol-
    compatible.
  - `ommit_ping=True` is REQUIRED — pyzk's connect() otherwise shells out
    to the OS `ping` command as a pre-flight check, which fails inside
    this app's Docker container (no `ping` binary / no raw-socket
    capability) even though the actual TCP connection works fine. Without
    this the client fails with "ZKNetworkError can't reach device" despite
    the device being perfectly reachable.
  - `get_attendance()` returns the device's ENTIRE stored log in one call
    (confirmed: 1091 records, no server-side date filtering available) —
    unlike Hikvision's ISAPI this needs no pagination/backfill machinery;
    the whole log is cheap enough to fetch and filter in-memory every
    sync (see zkteco_scheduler.py's module docstring for the trade-off).
  - Each Attendance record's `user_id` is a plain numeric string (e.g.
    "24005") — NOT the same as this app's Employee.user_id, which carries
    a department-letter prefix (e.g. "P24005"). Employee.full_name for
    that exact device user_id confirmed "Rislah Juana Dewi" / department
    "Plant" — the device's user_id is the NIK's numeric suffix with the
    prefix letter stripped. Resolved by numeric-suffix lookup against the
    Employee table (see zkteco_scheduler.py), not stored as employee_id
    verbatim.
  - `status` is the verification METHOD (fingerprint/face/card/...), not
    an in/out indicator. `punch` was 0 on every sample record — this
    terminal doesn't distinguish check-in/check-out itself either, same
    as the Hikvision terminal. Check-in/out is derived the same way:
    earliest event of the day = check-in, latest = check-out.
  - No `name` field on the Attendance record itself — resolved via
    get_users(), matching User.user_id (the same numeric string) to
    User.name.
"""
from typing import Optional


class ZKTecoError(Exception):
    pass


class ZKTecoClient:
    def __init__(self, ip: str, port: int = 4370, password: int = 0, timeout: int = 15):
        self.ip = ip
        self.port = port
        self.password = password or 0
        self.timeout = timeout

    def fetch(self) -> tuple[dict, list]:
        """Connects, pulls the full user roster and attendance log, then
        disconnects. Returns (name_by_device_user_id: {str: str},
        attendance: [(device_user_id: str, timestamp: datetime), ...]) —
        already stripped down to just what the scheduler needs."""
        from zk import ZK
        try:
            from zk.exception import ZKErrorConnection, ZKNetworkError
            network_errors = (ZKErrorConnection, ZKNetworkError, ConnectionError, OSError)
        except ImportError:
            network_errors = (ConnectionError, OSError)

        zk = ZK(self.ip, port=self.port, timeout=self.timeout, password=self.password,
                force_udp=False, ommit_ping=True)
        conn = None
        try:
            conn = zk.connect()
            name_by_id = {u.user_id: (u.name or "").strip() for u in conn.get_users()}
            attendance = [(a.user_id, a.timestamp) for a in conn.get_attendance()]
            return name_by_id, attendance
        except network_errors as e:
            raise ZKTecoError(f"Could not reach {self.ip}:{self.port}: {e}") from e
        except Exception as e:
            raise ZKTecoError(f"Device error ({self.ip}:{self.port}): {e}") from e
        finally:
            if conn:
                try:
                    conn.disconnect()
                except Exception:
                    pass
