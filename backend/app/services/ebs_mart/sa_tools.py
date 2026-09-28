"""
System Administration intent tools (library v2 section 3.2b): read-only
answers about EBS users, responsibilities, function access, SoD, profiles,
logins, concurrent processing, workflow approvals, patches and Forms
Personalization.

Three fences, all of which must fail for data to leak (blueprint v2 7):
  1. Open WebUI shows these tools, the EBS Support model and the prompts
     only to the ebs-sysadmin group;
  2. every function here checks the caller's email against
     SYSADMIN_ALLOWLIST (access.require on an sa_* mart) — a Keycloak group
     is never enough;
  3. the SQL runs as llm_sa_ro (query.run picks the SA reader for sa_*
     marts), the only role granted mart.sa_*.

Each tool reads sa_* marts only, so fence 3 needs no mixed connection.
"""
from app.services.ebs_mart import access, query
from app.services.ebs_mart.access import Caller
from app.services.ebs_mart.tools import _like, _val

# EBS's wall clock (WIB) — Oracle times are stored in it, PostgreSQL runs UTC.
_NOW = "(now() AT TIME ZONE 'Asia/Jakarta')"


def _run(caller: Caller, marts: str | list[str], sql: str, params: dict, tool: str, args: dict) -> dict:
    marts = [marts] if isinstance(marts, str) else marts
    for m in marts:
        try:
            access.require(caller, m)
        except access.AccessDenied as e:
            query.log_call(caller, tool=tool, marts=marts, args=args, status="DENIED", error=str(e))
            raise
    return query.run(caller, sql, params, tool=tool, marts=marts, args=args)


# A user argument matches the EBS user name exactly, or — when that finds
# nothing — the employee name, description or email as a substring.
_USER_MATCH = """(%(u)s::text IS NULL OR UPPER({a}.user_name) = UPPER(%(u)s::text)
                  OR (NOT EXISTS (SELECT 1 FROM mart.sa_user x WHERE UPPER(x.user_name) = UPPER(%(u)s::text))
                      AND ({a}.user_name ILIKE %(ul)s::text OR {a}.employee_name ILIKE %(ul)s::text
                           {extra})))"""


def _user_match(alias: str, with_contact: bool = False) -> str:
    extra = (f"OR {alias}.description ILIKE %(ul)s::text OR {alias}.email_address ILIKE %(ul)s::text"
             if with_contact else "")
    return _USER_MATCH.format(a=alias, extra=extra)


def sa_get_user(caller: Caller, user: str) -> dict:
    """Profile of one or more EBS users: status, dates, last login, linked
    employee and that employee's status."""
    args = {"user": user}
    sql = f"""
        SELECT user_name, employee_name, employee_number, employee_status, is_active, start_date, end_date,
               last_logon_date, days_since_login, never_logged_in, password_date, active_resp_count,
               description, email_address, is_seeded, termination_date
          FROM mart.sa_user u
         WHERE {_user_match('u', with_contact=True)}
         ORDER BY is_active DESC, user_name
    """
    return _run(caller, "sa_user", sql, {"u": _val(user), "ul": _like(user)}, "sa_get_user", args)


def sa_get_user_resps(caller: Caller, user: str, include_inactive: bool = False) -> dict:
    args = {"user": user, "include_inactive": include_inactive}
    sql = f"""
        SELECT user_name, employee_name, responsibility_name, app_short_name, grant_type, start_date, end_date,
               is_active, is_assignment_active, is_resp_active, is_user_active
          FROM mart.sa_user_resp u
         WHERE {_user_match('u')}
           AND (%(all)s OR is_active)
         ORDER BY user_name, is_active DESC, responsibility_name
    """
    return _run(caller, "sa_user_resp", sql, {"u": _val(user), "ul": _like(user), "all": include_inactive},
                "sa_get_user_resps", args)


def sa_who_has_resp(caller: Caller, responsibility: str, include_inactive: bool = False) -> dict:
    args = {"responsibility": responsibility, "include_inactive": include_inactive}
    sql = """
        SELECT responsibility_name, user_name, employee_name, grant_type, start_date, end_date, is_active,
               is_seeded
          FROM mart.sa_user_resp
         WHERE (responsibility_name ILIKE %(r)s::text OR responsibility_key ILIKE %(r)s::text)
           AND (%(all)s OR is_active)
         ORDER BY responsibility_name, user_name
    """
    return _run(caller, "sa_user_resp", sql, {"r": _like(responsibility), "all": include_inactive},
                "sa_who_has_resp", args)


def sa_who_has_function(caller: Caller, function: str, include_seeded: bool = False) -> dict:
    """Active users who can open a function, through which responsibility,
    and whether that grant is direct or indirect — one row per user ×
    responsibility. A function name that exists exactly ("Payments") is
    matched exactly; only when none does is it matched as a substring, so
    "Payments" does not also return "Invoice Apply Prepayments"."""
    args = {"function": function, "include_seeded": include_seeded}
    sql = """
        WITH fn AS (
            SELECT DISTINCT function_id FROM mart.sa_resp_function
             WHERE UPPER(function_name) = UPPER(%(f)s::text) OR UPPER(user_function_name) = UPPER(%(f)s::text)
        ), hit AS (
            SELECT f.* FROM mart.sa_resp_function f
             WHERE f.function_id IN (SELECT function_id FROM fn)
                OR (NOT EXISTS (SELECT 1 FROM fn) AND f.user_function_name ILIKE %(fl)s::text)
        )
        SELECT ur.user_name, ur.employee_name, ur.responsibility_name, ur.grant_type,
               STRING_AGG(DISTINCT hit.user_function_name, '; ') AS functions, ur.is_seeded
          FROM hit
          JOIN mart.sa_user_resp ur ON ur.responsibility_id = hit.responsibility_id
                                   AND ur.application_id = hit.application_id
         WHERE ur.is_active
           AND (%(seeded)s OR NOT ur.is_seeded)
         GROUP BY ur.user_name, ur.employee_name, ur.responsibility_name, ur.grant_type, ur.is_seeded
         ORDER BY ur.user_name, ur.responsibility_name
    """
    return _run(caller, ["sa_resp_function", "sa_user_resp"], sql,
                {"f": _val(function), "fl": _like(function), "seeded": include_seeded}, "sa_who_has_function", args)


def sa_get_resp_functions(caller: Caller, responsibility: str, function: str | None = None,
                          function_type: str | None = None, include_unheld: bool = False) -> dict:
    args = {"responsibility": responsibility, "function": function, "function_type": function_type,
            "include_unheld": include_unheld}
    sql = """
        SELECT responsibility_name, menu_name, user_function_name, function_name, function_type, is_resp_active,
               active_holders
          FROM mart.sa_resp_function
         WHERE responsibility_name ILIKE %(r)s::text
           AND (%(unheld)s OR active_holders > 0)
           AND (%(f)s::text IS NULL OR user_function_name ILIKE %(f)s::text OR function_name ILIKE %(f)s::text)
           AND (%(t)s::text IS NULL OR function_type = UPPER(%(t)s::text))
         ORDER BY responsibility_name, user_function_name
    """
    return _run(caller, "sa_resp_function", sql,
                {"r": _like(responsibility), "f": _like(function), "t": _val(function_type),
                 "unheld": include_unheld}, "sa_get_resp_functions", args)


def sa_get_resp_programs(caller: Caller, responsibility: str | None = None, program: str | None = None,
                         include_unheld: bool = False) -> dict:
    """What a responsibility may submit, or which responsibilities may submit
    a program. 'Semua program aplikasi' rows cover every program of that
    application and are returned for a program search when the program
    belongs to it."""
    if not _val(responsibility) and not _val(program):
        from app.services.ebs_mart.sql_guard import SqlRejected
        raise SqlRejected("Isi responsibility atau program (salah satu).")
    args = {"responsibility": responsibility, "program": program, "include_unheld": include_unheld}
    sql = """
        SELECT g.responsibility_name, g.request_group_name, g.unit_type, g.unit_short_name, g.unit_name,
               g.unit_app_short_name, g.program_enabled, g.active_holders
          FROM mart.sa_resp_request_group g
         WHERE (%(r)s::text IS NULL OR g.responsibility_name ILIKE %(r)s::text)
           AND (%(unheld)s OR g.active_holders > 0)
           AND (%(p)s::text IS NULL
                OR g.unit_name ILIKE %(p)s::text OR g.unit_short_name ILIKE %(p)s::text
                OR (g.unit_type = 'Semua program aplikasi' AND g.unit_app_short_name IN (
                        SELECT p.unit_app_short_name FROM mart.sa_resp_request_group p
                         WHERE p.unit_type = 'Program' AND (p.unit_name ILIKE %(p)s::text OR p.unit_short_name ILIKE %(p)s::text)
                        UNION
                        SELECT c.app_short_name FROM mart.sa_concurrent_request c
                         WHERE c.program_name ILIKE %(p)s::text OR c.program_short_name ILIKE %(p)s::text)))
         ORDER BY g.responsibility_name, g.unit_type, g.unit_name
    """
    return _run(caller, ["sa_resp_request_group", "sa_concurrent_request"], sql,
                {"r": _like(responsibility), "p": _like(program), "unheld": include_unheld},
                "sa_get_resp_programs", args)


def sa_get_dormant_users(caller: Caller, days: int = 90, exclude_seeded: bool = True) -> dict:
    """Active users who have not logged in for N days, or never."""
    args = {"days": days, "exclude_seeded": exclude_seeded}
    sql = """
        SELECT user_name, employee_name, employee_status, last_logon_date, days_since_login, never_logged_in,
               start_date, active_resp_count, is_seeded
          FROM mart.sa_user
         WHERE is_active
           AND (last_logon_date IS NULL OR days_since_login >= %(d)s)
           AND (NOT %(ex)s OR NOT is_seeded)
         ORDER BY never_logged_in DESC, days_since_login DESC NULLS FIRST, user_name
    """
    return _run(caller, "sa_user", sql, {"d": days, "ex": exclude_seeded}, "sa_get_dormant_users", args)


def sa_get_terminated_active_users(caller: Caller) -> dict:
    """Users still active in EBS whose employee is no longer active in HR."""
    sql = """
        SELECT user_name, employee_name, employee_number, employee_status, termination_date, last_logon_date,
               days_since_login, active_resp_count
          FROM mart.sa_user
         WHERE is_active AND employee_id IS NOT NULL AND employee_status <> 'Aktif'
         ORDER BY termination_date NULLS LAST, user_name
    """
    return _run(caller, "sa_user", sql, {}, "sa_get_terminated_active_users", {})


def sa_get_sod_violations(caller: Caller, rule_name: str | None = None, user: str | None = None,
                          include_seeded: bool = False) -> dict:
    args = {"rule_name": rule_name, "user": user, "include_seeded": include_seeded}
    sql = """
        SELECT risk, rule_name, user_name, employee_name, functions_a, responsibilities_a, functions_b,
               responsibilities_b, description, is_seeded
          FROM mart.sa_sod_violation
         WHERE (%(rn)s::text IS NULL OR rule_name ILIKE %(rn)s::text)
           AND (%(u)s::text IS NULL OR user_name ILIKE %(u)s::text OR employee_name ILIKE %(u)s::text)
           AND (%(seeded)s OR NOT is_seeded)
         ORDER BY risk_order, rule_name, user_name
    """
    return _run(caller, "sa_sod_violation", sql,
                {"rn": _like(rule_name), "u": _like(user), "seeded": include_seeded}, "sa_get_sod_violations", args)


def sa_get_profile_value(caller: Caller, profile: str, level: str | None = None,
                         value_owner: str | None = None) -> dict:
    """Values of a profile option per level. With value_owner = a user name,
    only the rows that can apply to that user are returned (their User
    level, the Responsibility level of their active responsibilities, then
    Application and Site) ordered by precedence — the first row wins for a
    given responsibility."""
    args = {"profile": profile, "level": level, "value_owner": value_owner}
    sql = """
        SELECT p.user_profile_name, p.profile_option_name, p.level_name, p.precedence, p.level_value_name,
               p.value, p.value_display, p.last_update_date
          FROM mart.sa_profile_value p
         WHERE (p.user_profile_name ILIKE %(p)s::text OR p.profile_option_name ILIKE %(p)s::text)
           AND (%(lv)s::text IS NULL OR p.level_name ILIKE %(lv)s::text)
           AND (%(o)s::text IS NULL
                OR p.level_id IN (10001, 10002)
                OR (p.level_id = 10004 AND UPPER(p.level_value_name) = UPPER(%(o)s::text))
                OR (p.level_id = 10003 AND EXISTS (
                        SELECT 1 FROM mart.sa_user_resp ur
                         WHERE UPPER(ur.user_name) = UPPER(%(o)s::text) AND ur.is_active
                           AND ur.responsibility_id = p.level_value
                           AND ur.application_id = p.level_value_app_id)))
         ORDER BY p.user_profile_name, p.precedence, p.level_value_name
    """
    marts = ["sa_profile_value"] + (["sa_user_resp"] if _val(value_owner) else [])
    return _run(caller, marts, sql, {"p": _like(profile), "lv": _val(level), "o": _val(value_owner)},
                "sa_get_profile_value", args)


def sa_get_login_history(caller: Caller, user: str, days: int = 7) -> dict:
    days = max(1, min(int(days or 7), 90))
    args = {"user": user, "days": days}
    sql = f"""
        SELECT user_name, employee_name, login_start, login_end, login_minutes, login_type, responsibility_name,
               user_form_name, form_name, form_start
          FROM mart.sa_login_audit u
         WHERE {_user_match('u')}
           AND login_start >= {_NOW}::date - %(d)s
         ORDER BY login_start DESC, form_start DESC NULLS LAST
    """
    return _run(caller, "sa_login_audit", sql, {"u": _val(user), "ul": _like(user), "d": days},
                "sa_get_login_history", args)


def sa_get_manager_status(caller: Caller, only_problems: bool = False) -> dict:
    args = {"only_problems": only_problems}
    sql = """
        SELECT manager_name, status_label, target_processes, actual_processes, running_requests, control_meaning,
               enabled_flag, target_node
          FROM mart.sa_concurrent_manager
         WHERE (NOT %(p)s OR status_label IN ('Kurang proses', 'Down (0 proses)'))
         ORDER BY CASE status_label WHEN 'Down (0 proses)' THEN 1 WHEN 'Kurang proses' THEN 2 WHEN 'Normal' THEN 3
                                    ELSE 4 END, manager_name
    """
    return _run(caller, "sa_concurrent_manager", sql, {"p": only_problems}, "sa_get_manager_status", args)


def sa_get_pending_approvals(caller: Caller, approver: str | None = None, days: int = 3,
                             item_type: str | None = None, include_fyi: bool = False,
                             include_errors: bool = False, group_by: str = "none") -> dict:
    """Open workflow notifications waiting at least N days. Workflow error
    notifications (WFERROR, POERROR, ... — tens of thousands sit open at
    SYSADMIN) are not approvals and are left out unless asked for."""
    args = {"approver": approver, "days": days, "item_type": item_type, "include_fyi": include_fyi,
            "include_errors": include_errors, "group_by": group_by}
    where = """
         WHERE days_open >= %(d)s
           AND (%(fyi)s OR requires_response)
           AND (%(err)s OR item_type NOT LIKE '%%ERROR')
           AND (%(a)s::text IS NULL OR recipient_role ILIKE %(a)s::text OR recipient_name ILIKE %(a)s::text)
           AND (%(it)s::text IS NULL OR item_type = UPPER(%(it)s::text) OR item_type_name ILIKE %(itl)s::text)
    """
    if group_by == "recipient":
        sql = f"""
            SELECT recipient_role, MAX(recipient_name) AS recipient_name, COUNT(*) AS jml_notifikasi,
                   MAX(days_open) AS terlama_hari, STRING_AGG(DISTINCT item_type_name, '; ') AS jenis
              FROM mart.sa_wf_open_notification {where}
             GROUP BY recipient_role ORDER BY jml_notifikasi DESC
        """
    elif group_by == "item_type":
        sql = f"""
            SELECT item_type, MAX(item_type_name) AS item_type_name, COUNT(*) AS jml_notifikasi,
                   MAX(days_open) AS terlama_hari, COUNT(DISTINCT recipient_role) AS jml_penerima
              FROM mart.sa_wf_open_notification {where}
             GROUP BY item_type ORDER BY jml_notifikasi DESC
        """
    else:
        sql = f"""
            SELECT item_type_name, item_type, user_key AS dokumen, subject, recipient_name, recipient_role,
                   begin_date, days_open, due_date, requires_response, notification_id
              FROM mart.sa_wf_open_notification {where}
             ORDER BY days_open DESC
        """
    return _run(caller, "sa_wf_open_notification", sql,
                {"d": days, "fyi": include_fyi, "err": include_errors, "a": _like(approver), "it": _val(item_type),
                 "itl": _like(item_type)},
                "sa_get_pending_approvals", args)


def sa_check_patch(caller: Caller, patch_number: str) -> dict:
    """Whether each patch (bug) number is applied, when, and in which
    languages. Several numbers may be given, separated by comma or space."""
    import re
    numbers = [n for n in re.split(r"[\s,;]+", patch_number or "") if n]
    args = {"patch_number": patch_number}
    sql = """
        SELECT n.bug_number, (p.bug_number IS NOT NULL) AS diterapkan, p.applied_date, p.application_short_name,
               p.language, p.aru_release_name
          FROM UNNEST(%(n)s::text[]) AS n(bug_number)
          LEFT JOIN mart.sa_patch p ON p.bug_number = n.bug_number
         ORDER BY n.bug_number, p.applied_date
    """
    return _run(caller, "sa_patch", sql, {"n": numbers}, "sa_check_patch", args)


def sa_get_form_personalizations(caller: Caller, form: str | None = None) -> dict:
    args = {"form": form}
    sql = """
        SELECT form_name, function_name, rule_level, sequence, description, trigger_event, trigger_object,
               condition_text, actions_enabled, last_update_date, last_updated_by
          FROM mart.sa_form_personalization
         WHERE (%(f)s::text IS NULL OR form_name ILIKE %(f)s::text OR function_name ILIKE %(f)s::text)
         ORDER BY form_name, function_name, sequence
    """
    return _run(caller, "sa_form_personalization", sql, {"f": _like(form)}, "sa_get_form_personalizations", args)


def it_get_concurrent_requests(caller: Caller, hours: int = 24, status: str | None = None,
                               program: str | None = None, user: str | None = None, phase: str | None = None,
                               group_by: str = "none") -> dict:
    """Concurrent requests of the last N hours (max 30 days), filtered by
    status (error/warning/...), phase, program or requester."""
    hours = max(1, min(int(hours or 24), 24 * 30))
    args = {"hours": hours, "status": status, "program": program, "user": user, "phase": phase,
            "group_by": group_by}
    status_map = {"error": ["E"], "warning": ["G"], "normal": ["C", "I", "R"], "terminated": ["X"],
                  "cancelled": ["D"], "hold": ["H"], "no manager": ["M"], "gagal": ["E", "X"]}
    codes = status_map.get((status or "").strip().lower()) if _val(status) else None
    where = f"""
         WHERE request_date >= {_NOW} - make_interval(hours => %(h)s)
           AND ((%(sc)s::text[] IS NULL AND %(sl)s::text IS NULL)
                OR status_code = ANY(%(sc)s::text[]) OR status ILIKE %(sl)s::text)
           AND (%(ph)s::text IS NULL OR phase ILIKE %(ph)s::text)
           AND (%(p)s::text IS NULL OR program_name ILIKE %(pl)s::text OR program_short_name ILIKE %(pl)s::text)
           AND (%(u)s::text IS NULL OR requested_by ILIKE %(ul)s::text OR employee_name ILIKE %(ul)s::text)
    """
    if group_by == "program":
        sql = f"""
            SELECT program_name, program_short_name, COUNT(*) AS jml_request,
                   COUNT(*) FILTER (WHERE status_code = 'E') AS error, COUNT(*) FILTER (WHERE status_code = 'G') AS warning,
                   ROUND(AVG(run_minutes), 1) AS rata2_menit, MAX(run_minutes) AS maks_menit
              FROM mart.sa_concurrent_request {where}
             GROUP BY program_name, program_short_name ORDER BY jml_request DESC
        """
    elif group_by == "status":
        sql = f"""
            SELECT phase, status, COUNT(*) AS jml_request
              FROM mart.sa_concurrent_request {where}
             GROUP BY phase, status ORDER BY jml_request DESC
        """
    else:
        sql = f"""
            SELECT request_id, program_name, requested_by, responsibility_name, phase, status, request_date,
                   actual_start_date, actual_completion_date, run_minutes, wait_minutes, completion_text,
                   argument_text, queue_name, parent_request_id
              FROM mart.sa_concurrent_request {where}
             ORDER BY request_date DESC
        """
    return _run(caller, "sa_concurrent_request", sql,
                {"h": hours, "sc": codes, "sl": _like(status) if _val(status) and not codes else None,
                 "ph": _val(phase), "p": _val(program), "pl": _like(program), "u": _val(user), "ul": _like(user)},
                "it_get_concurrent_requests", args)


def it_get_interface_errors(caller: Caller, interface: str | None = None, status: str | None = None,
                            days: int | None = None, group_by: str = "summary") -> dict:
    """Open-interface rows in error or still waiting: AP invoice import, AR
    AutoInvoice, GL journal import, inventory (MTI and pending MMTT) and
    receiving. summary = count, oldest and example per interface × status ×
    error; detail = the rows."""
    args = {"interface": interface, "status": status, "days": days, "group_by": group_by}
    where = """
         WHERE (%(i)s::text IS NULL OR interface_name ILIKE %(il)s::text)
           AND (%(s)s::text IS NULL OR status = UPPER(%(s)s::text))
           AND (%(d)s::int IS NULL OR age_days <= %(d)s::int)
           AND status <> 'PROCESSED'
    """
    if group_by == "detail":
        sql = f"""
            SELECT interface_name, source, doc_ref, status, error_code, error_message, txn_date, created_date, age_days,
                   amount, quantity, item_code, request_id, row_count
              FROM mart.sa_interface_error {where}
             ORDER BY interface_name, created_date
        """
    else:
        sql = f"""
            SELECT interface_name, status, COALESCE(error_message, error_code) AS error, SUM(row_count) AS jml_baris,
                   MIN(created_date) AS tertua, MAX(created_date) AS terbaru,
                   (ARRAY_AGG(doc_ref ORDER BY created_date))[1:3] AS contoh
              FROM mart.sa_interface_error {where}
             GROUP BY interface_name, status, COALESCE(error_message, error_code)
             ORDER BY interface_name, jml_baris DESC
        """
    return _run(caller, "sa_interface_error", sql,
                {"i": _val(interface), "il": _like(interface), "s": _val(status), "d": days},
                "it_get_interface_errors", args)
