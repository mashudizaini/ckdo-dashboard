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
from typing import Iterable, List, Optional

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


def clean_department_list(raw_values: Iterable[Optional[str]]) -> List[str]:
    """Turn a bag of raw department strings (straight from `SELECT DISTINCT`,
    possibly unioned across tables) into a clean, sorted list fit for a
    filter dropdown: drops blanks and numeric-junk values (e.g. "15" from a
    known Excel column-shift bug that a couple of `employees` rows still
    carry, pending manual HR correction), and collapses case-only
    duplicates ("Plant" / "PLANT") to a single display label, preferring
    the non-all-caps variant."""
    groups: dict = {}
    for v in raw_values:
        if not v or v.strip().isdigit():
            continue
        v = v.strip()
        groups.setdefault(v.upper(), []).append(v)
    display = {}
    for key, variants in groups.items():
        non_caps = [v for v in variants if v != v.upper()]
        display[key] = non_caps[0] if non_caps else variants[0]
    return sorted(display.values())
