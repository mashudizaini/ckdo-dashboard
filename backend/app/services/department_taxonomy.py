"""
Canonical department taxonomy shared across HR/Attendance/Leave modules.

The company recognizes exactly 4 operational departments: Administration,
Sales & Marketing, Strategy & Development, Plant. Historically, uploaded
attendance data (Intercom/Talenta/Plant exports) sometimes carried a more
granular or inconsistently-cased raw value straight into
AttendanceRecord.department whenever the upload's employee_id didn't match
anyone in the Employee master (the normal path — copying department from
the Employee master — silently no-ops in that case). This map exists so
*future* uploads don't reintroduce that mess; a one-time data migration
(2026-08-10) already cleaned up existing rows using the same mapping.
"""
from typing import Optional

CANONICAL_DEPARTMENTS = ["Administration", "Sales & Marketing", "Strategy & Development", "Plant"]

_RAW_TO_CANONICAL = {
    "ADMINISTRATION":        "Administration",
    "DIRECTOR":              "Administration",
    "SALES & MARKETING":     "Sales & Marketing",
    "MKT & BD":              "Sales & Marketing",
    "STRATEGY DEVELOPMENT":  "Strategy & Development",
    "STRATEGY & DEVELOPMENT":"Strategy & Development",
    "RA & BD":               "Strategy & Development",
    "PLANT":                 "Plant",
    "VALIDATION":            "Plant",
    "QA":                    "Plant",
    "QM":                    "Plant",
}


def normalize_department(raw: Optional[str]) -> Optional[str]:
    """Best-effort mapping of a raw department string to one of the 4
    canonical departments. Returns None if unrecognized (caller should keep
    whatever it already had rather than overwrite with a guess) — this
    includes Intercom's "All Departments" placeholder, which carries no
    real department info at all."""
    if not raw:
        return None
    key = raw.strip().upper()
    if key == "ALL DEPARTMENTS":
        return None
    return _RAW_TO_CANONICAL.get(key)
