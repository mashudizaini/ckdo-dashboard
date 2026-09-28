"""
ETL for the System Administration domain (blueprint v2 section 4.7), phase 6.
Oracle EBS FND / WF / AD -> core.sa_* -> REFRESH mart.sa_*.

  etl_mart_sa      daily: users, responsibilities (direct + indirect),
                   responsibility -> function (compiled menus + exclusions),
                   request groups, profile values, login audit (90 days,
                   incremental), patches, Forms Personalization.
  etl_mart_sa_ops  every 10 minutes: concurrent requests (30 days,
                   incremental), concurrent managers, open workflow
                   notifications. Its own job and advisory lock, so a slow
                   daily run never holds back the operational picture.

Never extracted: FND_USER's encrypted password columns, and any profile
option whose name reads like a credential (PROFILE_BLACKLIST_REGEX, applied
in the Oracle WHERE clause and again here before insert).

Same conventions as ebs_mart_tasks.py: logged in eis.etl_job_log, one
advisory lock per job, marts refreshed before the run is marked successful,
and celery must be restarted after a deploy that touches this file.
"""
import logging
import re

from psycopg2.extras import execute_values

from app.database import get_oracle_connection
from app.services.ebs_mart.constants import SA_LOGIN_DAYS, SA_REQUEST_DAYS
from app.services.ebs_mart.sa_sql import PROFILE_BLACKLIST_REGEX
from app.tasks.celery_app import celery_app
from app.tasks.ebs_mart_tasks import (
    _BATCH, _Run, _get_watermark, _int, _set_watermark, _upsert, refresh_marts_for_job,
)

logger = logging.getLogger(__name__)

_BLACKLIST = re.compile(PROFILE_BLACKLIST_REGEX, re.I)


def _q(cur_ora, label: str, sql: str, params: dict | None = None):
    """One extract; a failure names the stream, so the job log says which
    FND table or column this instance does not have."""
    try:
        cur_ora.execute(sql, params or {})
        return cur_ora.fetchall()
    except Exception as e:
        raise RuntimeError(f"extract {label}: {e}") from e


def _replace(cur, table: str, columns: list[str], rows: list[tuple]) -> int:
    """Full snapshot: empty the table and load it again, inside the run's
    transaction, so the mart refresh never sees it half-loaded."""
    cur.execute(f"DELETE FROM {table}")
    if rows:
        execute_values(cur, f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s", rows, page_size=_BATCH)
    return len(rows)


# ── Daily: identity and access ──────────────────────────────────────────────

_USER_SQL = """
    SELECT fu.user_id, fu.user_name, SUBSTR(fu.description, 1, 240), SUBSTR(fu.email_address, 1, 240),
           fu.start_date, fu.end_date, fu.last_logon_date, fu.password_date, fu.employee_id,
           papf.employee_number, SUBSTR(papf.full_name, 1, 240), papf.current_employee_flag,
           (SELECT MAX(pps.actual_termination_date) FROM per_periods_of_service pps
             WHERE pps.person_id = fu.employee_id),
           fu.created_by, fu.creation_date
      FROM fnd_user fu
      LEFT JOIN per_all_people_f papf
             ON papf.person_id = fu.employee_id
            AND TRUNC(SYSDATE) BETWEEN papf.effective_start_date AND papf.effective_end_date
"""
_USER_COLS = ["user_id", "user_name", "description", "email_address", "start_date", "end_date", "last_logon_date",
              "password_date", "employee_id", "employee_number", "employee_name", "current_employee_flag",
              "termination_date", "created_by", "creation_date"]

# Active employees with an email (the row effective today of a current
# employee) — EBS Chat's identity source, see core.hr_ebs_employee.
_EMPLOYEE_SQL = """
    SELECT papf.person_id, papf.employee_number, SUBSTR(papf.full_name, 1, 240),
           LOWER(TRIM(papf.email_address))
      FROM per_all_people_f papf
     WHERE TRUNC(SYSDATE) BETWEEN papf.effective_start_date AND papf.effective_end_date
       AND papf.current_employee_flag = 'Y'
       AND papf.email_address IS NOT NULL
"""

_RESP_SQL = """
    SELECT fr.responsibility_id, fr.application_id, fa.application_short_name, fr.responsibility_key,
           frt.responsibility_name, SUBSTR(frt.description, 1, 240), fr.menu_id, fr.request_group_id,
           fr.group_application_id, fr.start_date, fr.end_date, fr.version
      FROM fnd_responsibility fr
      JOIN fnd_responsibility_tl frt ON frt.responsibility_id = fr.responsibility_id
                                    AND frt.application_id = fr.application_id AND frt.language = 'US'
      JOIN fnd_application fa        ON fa.application_id = fr.application_id
"""
_RESP_COLS = ["resp_id", "app_id", "app_short_name", "resp_key", "resp_name", "description", "menu_id",
              "request_group_id", "group_application_id", "start_date", "end_date", "version"]

# Blueprint v2's user × responsibility extract, direct and indirect (UMX
# roles), collapsed to one row per grant: a responsibility inherited through
# two roles is one grant with the widest dates.
_USER_RESP_SQL = """
    SELECT user_id, responsibility_id, responsibility_application_id, NVL(security_group_id, 0), grant_type,
           MIN(start_date), NULLIF(MAX(NVL(end_date, DATE '4712-12-31')), DATE '4712-12-31')
      FROM (SELECT user_id, responsibility_id, responsibility_application_id, security_group_id,
                   start_date, end_date, 'DIRECT' AS grant_type
              FROM fnd_user_resp_groups_direct
            UNION ALL
            SELECT user_id, responsibility_id, responsibility_application_id, security_group_id,
                   start_date, end_date, 'INDIRECT'
              FROM fnd_user_resp_groups_indirect)
     GROUP BY user_id, responsibility_id, responsibility_application_id, NVL(security_group_id, 0), grant_type
"""

# The menus whose functions matter: every held responsibility's menu, and
# every menu some responsibility excludes (to subtract its functions).
_HELD_MENUS = """
    SELECT fr.menu_id FROM fnd_responsibility fr
     WHERE (fr.responsibility_id, fr.application_id) IN
           (SELECT responsibility_id, responsibility_application_id FROM fnd_user_resp_groups_direct
            UNION
            SELECT responsibility_id, responsibility_application_id FROM fnd_user_resp_groups_indirect)
    UNION
    SELECT rf.action_id FROM fnd_resp_functions rf WHERE rf.rule_type = 'M'
"""
# FND_COMPILED_MENU_FUNCTIONS is EBS's own flattened, grant-checked menu
# tree (kept current by "Compile Security"), so no CONNECT BY is needed.
_MENU_FN_SQL = f"""
    SELECT DISTINCT cmf.menu_id, cmf.function_id
      FROM fnd_compiled_menu_functions cmf
     WHERE cmf.grant_flag = 'Y'
       AND cmf.menu_id IN ({_HELD_MENUS})
"""
_FUNCTION_SQL = """
    SELECT function_id, function_name, SUBSTR(user_function_name, 1, 240), type, SUBSTR(description, 1, 240)
      FROM fnd_form_functions_vl
"""
_MENU_SQL = "SELECT menu_id, menu_name, SUBSTR(user_menu_name, 1, 240) FROM fnd_menus_vl"
_EXCL_SQL = "SELECT DISTINCT responsibility_id, application_id, rule_type, action_id FROM fnd_resp_functions"

_APP_SQL = "SELECT application_id, application_short_name, SUBSTR(application_name, 1, 240) FROM fnd_application_vl"
_PROGRAM_SQL = """
    SELECT concurrent_program_id, application_id, concurrent_program_name,
           SUBSTR(user_concurrent_program_name, 1, 240), enabled_flag
      FROM fnd_concurrent_programs_vl
"""
_REQSET_SQL = """
    SELECT request_set_id, application_id, request_set_name, SUBSTR(user_request_set_name, 1, 240)
      FROM fnd_request_sets_vl
"""
_RG_UNIT_SQL = """
    SELECT rgu.request_group_id, rgu.application_id, rg.request_group_name, rgu.request_unit_type,
           rgu.request_unit_id, rgu.unit_application_id
      FROM fnd_request_group_units rgu
      JOIN fnd_request_groups rg ON rg.request_group_id = rgu.request_group_id
                                AND rg.application_id = rgu.application_id
"""

# Credential-like profiles never leave Oracle (blueprint v2). Level names
# are resolved here; MO security profile and operating unit values get a
# readable name next to the stored id.
_PROFILE_SQL = f"""
    SELECT po.profile_option_id, po.application_id, po.profile_option_name,
           SUBSTR(po.user_profile_option_name, 1, 240), pov.level_id, pov.level_value,
           pov.level_value_application_id,
           CASE pov.level_id
                WHEN 10001 THEN 'Site'
                WHEN 10002 THEN (SELECT a.application_short_name FROM fnd_application a
                                  WHERE a.application_id = pov.level_value)
                WHEN 10003 THEN (SELECT t.responsibility_name FROM fnd_responsibility_tl t
                                  WHERE t.responsibility_id = pov.level_value
                                    AND t.application_id = pov.level_value_application_id AND t.language = 'US')
                WHEN 10004 THEN (SELECT u.user_name FROM fnd_user u WHERE u.user_id = pov.level_value)
                WHEN 10005 THEN (SELECT n.node_name FROM fnd_nodes n WHERE n.node_id = pov.level_value)
                WHEN 10006 THEN (SELECT o.name FROM hr_all_organization_units o
                                  WHERE o.organization_id = pov.level_value)
                ELSE TO_CHAR(pov.level_value) END,
           SUBSTR(pov.profile_option_value, 1, 240),
           CASE WHEN REGEXP_LIKE(pov.profile_option_value, '^[0-9]+$') THEN
                CASE po.profile_option_name
                     WHEN 'XLA_MO_SECURITY_PROFILE_LEVEL' THEN
                          (SELECT sp.security_profile_name FROM per_security_profiles sp
                            WHERE sp.security_profile_id = TO_NUMBER(pov.profile_option_value))
                     WHEN 'ORG_ID' THEN
                          (SELECT o.name FROM hr_all_organization_units o
                            WHERE o.organization_id = TO_NUMBER(pov.profile_option_value))
                     WHEN 'DEFAULT_ORG_ID' THEN
                          (SELECT o.name FROM hr_all_organization_units o
                            WHERE o.organization_id = TO_NUMBER(pov.profile_option_value))
                END
           END,
           pov.last_update_date
      FROM fnd_profile_option_values pov
      JOIN fnd_profile_options_vl po ON po.profile_option_id = pov.profile_option_id
                                    AND po.application_id = pov.application_id
     WHERE NOT REGEXP_LIKE(po.profile_option_name || ' ' || po.user_profile_option_name,
                           '{PROFILE_BLACKLIST_REGEX}', 'i')
"""
_PROFILE_COLS = ["row_key", "profile_option_id", "profile_app_id", "profile_name", "user_profile_name", "level_id",
                 "level_value", "level_value_app_id", "level_value_name", "value", "value_display",
                 "last_update_date"]

# Sessions × responsibility × form. Responsibility and form detail exist only
# when Sign-On:Audit Level is Responsibility or Form.
_LOGIN_SQL = """
    SELECT l.login_id, l.user_id, l.start_time, l.end_time, l.login_type, SUBSTR(l.terminal_id, 1, 60),
           lr.login_resp_id, lr.responsibility_id, lr.resp_appl_id, lr.start_time, lr.end_time,
           lrf.form_id, lrf.form_appl_id, f.form_name, SUBSTR(f.user_form_name, 1, 240),
           lrf.start_time, lrf.end_time
      FROM fnd_logins l
      LEFT JOIN fnd_login_responsibilities lr ON lr.login_id = l.login_id
      LEFT JOIN fnd_login_resp_forms lrf      ON lrf.login_id = lr.login_id AND lrf.login_resp_id = lr.login_resp_id
      LEFT JOIN fnd_form_vl f                 ON f.form_id = lrf.form_id AND f.application_id = lrf.form_appl_id
     WHERE l.start_time >= :since
"""
_LOGIN_COLS = ["row_key", "login_id", "user_id", "login_start", "login_end", "login_type", "terminal_id",
               "login_resp_id", "resp_id", "resp_app_id", "resp_start", "resp_end", "form_id", "form_app_id",
               "form_name", "user_form_name", "form_start", "form_end"]

_PATCH_SQL = """
    SELECT bug_id, bug_number, application_short_name, creation_date, last_update_date, language,
           aru_release_name, trackable_entity_abbr, baseline_name
      FROM ad_bugs
"""
_PATCH_COLS = ["row_key", "bug_id", "bug_number", "application_short_name", "applied_date", "last_update_date",
               "language", "aru_release_name", "trackable_entity", "baseline_name"]

_FORM_RULE_SQL = """
    SELECT r.id, r.function_name, r.form_name, r.sequence, SUBSTR(r.description, 1, 240), r.rule_type, r.enabled,
           r.trigger_event, SUBSTR(r.trigger_object, 1, 240), SUBSTR(r.condition, 1, 1000),
           (SELECT COUNT(*) FROM fnd_form_custom_actions a WHERE a.rule_id = r.id AND a.enabled = 'Y'),
           r.last_update_date, r.last_updated_by
      FROM fnd_form_custom_rules r
"""
_FORM_RULE_COLS = ["rule_id", "function_name", "form_name", "sequence", "description", "rule_type", "enabled",
                   "trigger_event", "trigger_object", "condition_text", "actions_enabled", "last_update_date",
                   "last_updated_by"]


@celery_app.task(name="app.tasks.etl_tasks.etl_mart_sa")
def etl_mart_sa(year: int = None, month: int = None, full_refresh: bool = False,
                trigger_type: str = "SCHEDULE", triggered_by: str | None = None):
    """Daily System Administration snapshot. Everything but the login audit
    is a full reload (masters and grants: a revoked grant is a deleted row,
    which only a full reload notices); logins are incremental over a
    rolling SA_LOGIN_DAYS window."""
    job = "etl_mart_sa"
    run = _Run(job, trigger_type, triggered_by, {"full_refresh": full_refresh})
    if not run.locked:
        run.finish("skipped", error="Job yang sama sedang berjalan (advisory lock) — dilewati.")
        run.close()
        return {"status": "skipped"}

    rows_read = rows_upserted = 0
    try:
        cur = run.cur
        wm_login = None if full_refresh else _get_watermark(cur, job, "logins")
        ora = get_oracle_connection()
        try:
            co = ora.cursor()
            co.arraysize = _BATCH
            users = _q(co, "fnd_user", _USER_SQL)
            employees = _q(co, "per_all_people_f", _EMPLOYEE_SQL)
            resps = _q(co, "fnd_responsibility", _RESP_SQL)
            user_resps = _q(co, "fnd_user_resp_groups", _USER_RESP_SQL)
            menu_fns = _q(co, "fnd_compiled_menu_functions", _MENU_FN_SQL)
            functions = _q(co, "fnd_form_functions", _FUNCTION_SQL)
            menus = _q(co, "fnd_menus", _MENU_SQL)
            excls = _q(co, "fnd_resp_functions", _EXCL_SQL)
            apps = _q(co, "fnd_application", _APP_SQL)
            programs = _q(co, "fnd_concurrent_programs", _PROGRAM_SQL)
            reqsets = _q(co, "fnd_request_sets", _REQSET_SQL)
            rg_units = _q(co, "fnd_request_group_units", _RG_UNIT_SQL)
            profiles = _q(co, "fnd_profile_option_values", _PROFILE_SQL)
            # One day of overlap: a session seen while still open gets its
            # end time on the next run.
            since_sql = f"GREATEST(SYSDATE - {SA_LOGIN_DAYS}, :wm - 1)" if wm_login else f"SYSDATE - {SA_LOGIN_DAYS}"
            logins = _q(co, "fnd_logins", _LOGIN_SQL.replace(":since", since_sql),
                        {"wm": wm_login} if wm_login else {})
            patches = _q(co, "ad_bugs", _PATCH_SQL)
            form_rules = _q(co, "fnd_form_custom_rules", _FORM_RULE_SQL)
        finally:
            ora.close()
        rows_read = sum(map(len, (users, employees, resps, user_resps, menu_fns, functions, menus, excls, apps, programs,
                                  reqsets, rg_units, profiles, logins, patches, form_rules)))
        if not menu_fns:
            raise RuntimeError("FND_COMPILED_MENU_FUNCTIONS kosong untuk menu responsibility yang dipakai — "
                               "jalankan concurrent program 'Compile Security' di EBS, lalu ulangi job ini.")

        n = 0
        n += _replace(cur, "core.hr_ebs_employee", ["person_id", "employee_number", "full_name", "email"],
                      [(_int(r[0]), r[1], r[2], r[3]) for r in employees])
        n += _replace(cur, "core.sa_user", _USER_COLS, [
            (_int(r[0]), r[1], r[2], r[3], r[4], r[5], r[6], r[7], _int(r[8]), r[9], r[10], r[11], r[12],
             _int(r[13]), r[14]) for r in users])
        n += _replace(cur, "core.sa_resp", _RESP_COLS, [
            (_int(r[0]), _int(r[1]), r[2], r[3], r[4], r[5], _int(r[6]), _int(r[7]), _int(r[8]), r[9], r[10], r[11])
            for r in resps])
        n += _replace(cur, "core.sa_user_resp",
                      ["row_key", "user_id", "resp_id", "app_id", "security_group_id", "grant_type", "start_date",
                       "end_date"],
                      [(f"{int(r[0])}|{int(r[1])}|{int(r[2])}|{int(r[3])}|{r[4]}", _int(r[0]), _int(r[1]), _int(r[2]),
                        _int(r[3]), r[4], r[5], r[6]) for r in user_resps])
        n += _replace(cur, "core.sa_menu_function", ["menu_id", "function_id"],
                      [(_int(r[0]), _int(r[1])) for r in menu_fns])
        n += _replace(cur, "core.sa_function",
                      ["function_id", "function_name", "user_function_name", "function_type", "description"],
                      [(_int(r[0]), r[1], r[2], r[3], r[4]) for r in functions])
        n += _replace(cur, "core.sa_menu", ["menu_id", "menu_name", "user_menu_name"],
                      [(_int(r[0]), r[1], r[2]) for r in menus])
        n += _replace(cur, "core.sa_resp_exclusion", ["resp_id", "app_id", "rule_type", "action_id"],
                      [(_int(r[0]), _int(r[1]), r[2], _int(r[3])) for r in excls if r[3] is not None])
        n += _replace(cur, "core.sa_application", ["app_id", "short_name", "name"],
                      [(_int(r[0]), r[1], r[2]) for r in apps])
        n += _replace(cur, "core.sa_conc_program",
                      ["program_id", "app_id", "program_short_name", "program_name", "enabled_flag"],
                      [(_int(r[0]), _int(r[1]), r[2], r[3], r[4]) for r in programs])
        n += _replace(cur, "core.sa_request_set", ["set_id", "app_id", "set_short_name", "set_name"],
                      [(_int(r[0]), _int(r[1]), r[2], r[3]) for r in reqsets])
        n += _replace(cur, "core.sa_request_group_unit",
                      ["row_key", "request_group_id", "rg_app_id", "request_group_name", "unit_type", "unit_id",
                       "unit_app_id"],
                      [(f"{int(r[0])}|{int(r[1])}|{r[3]}|{_int(r[4])}|{_int(r[5])}", _int(r[0]), _int(r[1]), r[2],
                        r[3], _int(r[4]), _int(r[5])) for r in rg_units])
        # Second fence for the credential blacklist, in case a profile's
        # user name only matches in a language the Oracle side did not see.
        n += _replace(cur, "core.sa_profile_value", _PROFILE_COLS, [
            (f"{int(r[0])}|{int(r[1])}|{r[4]}|{_int(r[5])}|{_int(r[6])}", _int(r[0]), _int(r[1]), r[2], r[3],
             _int(r[4]), _int(r[5]), _int(r[6]), r[7], r[8], r[9], r[10])
            for r in profiles if not _BLACKLIST.search(f"{r[2]} {r[3] or ''}")])
        n += _replace(cur, "core.sa_patch", _PATCH_COLS, [
            (f"{int(r[0])}", _int(r[0]), r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8]) for r in patches])
        n += _replace(cur, "core.sa_form_rule", _FORM_RULE_COLS, [
            (_int(r[0]), r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], _int(r[10]), r[11], _int(r[12]))
            for r in form_rules])

        login_rows = {}
        for r in logins:
            key = f"{int(r[0])}|{_int(r[6]) or ''}|{_int(r[11]) or ''}|{_int(r[12]) or ''}|{r[15] or ''}"
            login_rows[key] = (key, _int(r[0]), _int(r[1]), r[2], r[3], r[4], r[5], _int(r[6]), _int(r[7]),
                               _int(r[8]), r[9], r[10], _int(r[11]), _int(r[12]), r[13], r[14], r[15], r[16])
        if full_refresh:
            cur.execute("DELETE FROM core.sa_login")
        n += _upsert(cur, "core.sa_login", _LOGIN_COLS, ["row_key"], list(login_rows.values()))
        cur.execute(f"DELETE FROM core.sa_login WHERE login_start < now() - interval '{SA_LOGIN_DAYS} days'")
        new_wm = max((r[3] for r in login_rows.values() if r[3]), default=None)
        _set_watermark(cur, job, "logins", new_wm)
        rows_upserted = n

        run.pg.commit()
        refresh_marts_for_job(job)
        run.finish("success", rows_read, rows_upserted, wm_from=wm_login, wm_to=new_wm or wm_login)
        logger.info("[%s] read=%s loaded=%s users=%s grants=%s menu_fns=%s logins=%s", job, rows_read,
                    rows_upserted, len(users), len(user_resps), len(menu_fns), len(logins))
    except Exception as e:
        run.pg.rollback()
        logger.error("[%s] failed: %s", job, e)
        run.finish("failed", rows_read, rows_upserted, error=str(e))
        run.close()
        raise
    run.close()
    return {"status": "success", "rows_read": rows_read, "rows_upserted": rows_upserted}


# ── Every 10 minutes: concurrent processing and workflow ────────────────────

_REQUEST_WM = "r.last_update_date"
_REQUEST_SQL = f"""
    SELECT r.request_id, r.parent_request_id, r.concurrent_program_id, r.program_application_id, r.requested_by,
           r.responsibility_id, r.responsibility_application_id, r.phase_code, r.status_code, r.request_date,
           r.requested_start_date, r.actual_start_date, r.actual_completion_date,
           SUBSTR(r.completion_text, 1, 500), SUBSTR(r.argument_text, 1, 240), r.hold_flag, r.priority,
           (SELECT q.user_concurrent_queue_name
              FROM fnd_concurrent_processes p
              JOIN fnd_concurrent_queues_vl q ON q.concurrent_queue_id = p.concurrent_queue_id
                                             AND q.application_id = p.queue_application_id
             WHERE p.concurrent_process_id = r.controlling_manager),
           r.last_update_date
      FROM fnd_concurrent_requests r
     WHERE r.request_date >= SYSDATE - {SA_REQUEST_DAYS}
       {{wm}}
"""
_REQUEST_COLS = ["request_id", "parent_request_id", "program_id", "program_app_id", "requested_by", "resp_id",
                 "resp_app_id", "phase_code", "status_code", "request_date", "requested_start_date",
                 "actual_start_date", "actual_completion_date", "completion_text", "argument_text", "hold_flag",
                 "priority", "queue_name", "src_last_update"]

_MANAGER_SQL = """
    SELECT q.concurrent_queue_id, q.application_id, q.concurrent_queue_name, SUBSTR(q.user_concurrent_queue_name, 1, 240),
           q.max_processes, q.running_processes, q.enabled_flag, q.control_code,
           (SELECT l.meaning FROM fnd_lookups l WHERE l.lookup_type = 'CP_CONTROL_CODE' AND l.lookup_code = q.control_code),
           q.target_node, q.manager_type
      FROM fnd_concurrent_queues_vl q
"""
_MANAGER_COLS = ["queue_key", "queue_id", "app_id", "queue_short_name", "manager_name", "max_processes",
                 "running_processes", "enabled_flag", "control_code", "control_meaning", "target_node", "manager_type"]

# Open notifications. The document behind one comes from WF_ITEMS.USER_KEY
# (PO number, requisition number...), reached through the notification's
# context "ITEM_TYPE:ITEM_KEY:ACTIVITY_ID". requires_response separates
# approvals waiting for someone from FYI messages nobody ever closes.
_WF_SQL = """
    SELECT n.notification_id, n.message_type,
           (SELECT it.display_name FROM wf_item_types_vl it WHERE it.name = n.message_type),
           n.message_name, n.recipient_role, SUBSTR(n.to_user, 1, 240), n.original_recipient,
           SUBSTR(n.from_user, 1, 240), n.more_info_role, n.mail_status, n.begin_date, n.due_date,
           SUBSTR(n.subject, 1, 240), n.ctx_item_key,
           (SELECT i.user_key FROM wf_items i WHERE i.item_type = n.ctx_item_type AND i.item_key = n.ctx_item_key),
           CASE WHEN EXISTS (SELECT 1 FROM wf_message_attributes ma
                              WHERE ma.message_type = n.message_type AND ma.message_name = n.message_name
                                AND ma.subtype = 'RESPOND') THEN 'Y' ELSE 'N' END
      FROM (SELECT wn.notification_id, wn.message_type, wn.message_name, wn.recipient_role, wn.to_user,
                   wn.original_recipient, wn.from_user, wn.more_info_role, wn.mail_status, wn.begin_date,
                   wn.due_date, wn.subject,
                   SUBSTR(wn.context, 1, INSTR(wn.context, ':') - 1) AS ctx_item_type,
                   SUBSTR(wn.context, INSTR(wn.context, ':') + 1,
                          INSTR(wn.context, ':', -1) - INSTR(wn.context, ':') - 1) AS ctx_item_key
              FROM wf_notifications wn
             WHERE wn.status = 'OPEN') n
"""
_WF_COLS = ["notification_id", "item_type", "item_type_name", "message_name", "recipient_role", "recipient_name",
            "original_recipient", "from_user", "more_info_role", "mail_status", "begin_date", "due_date", "subject",
            "item_key", "user_key", "requires_response"]


@celery_app.task(name="app.tasks.etl_tasks.etl_mart_sa_ops")
def etl_mart_sa_ops(year: int = None, month: int = None, full_refresh: bool = False,
                    trigger_type: str = "SCHEDULE", triggered_by: str | None = None):
    """Concurrent requests (incremental on last_update_date, rolling
    SA_REQUEST_DAYS window), concurrent managers and open workflow
    notifications (both full snapshots — small, and a closed notification
    must disappear)."""
    job = "etl_mart_sa_ops"
    run = _Run(job, trigger_type, triggered_by, {"full_refresh": full_refresh})
    if not run.locked:
        run.finish("skipped", error="Job yang sama sedang berjalan (advisory lock) — dilewati.")
        run.close()
        return {"status": "skipped"}

    rows_read = rows_upserted = 0
    wm = None
    try:
        cur = run.cur
        wm = None if full_refresh else _get_watermark(cur, job, "requests")
        ora = get_oracle_connection()
        try:
            co = ora.cursor()
            co.arraysize = _BATCH
            sql = _REQUEST_SQL.format(wm=f"AND {_REQUEST_WM} >= :wm - 1/24" if wm else "")
            requests = _q(co, "fnd_concurrent_requests", sql, {"wm": wm} if wm else {})
            managers = _q(co, "fnd_concurrent_queues", _MANAGER_SQL)
            notifs = _q(co, "wf_notifications", _WF_SQL)
        finally:
            ora.close()
        rows_read = len(requests) + len(managers) + len(notifs)

        if full_refresh:
            cur.execute("DELETE FROM core.sa_conc_request")
        n = _upsert(cur, "core.sa_conc_request", _REQUEST_COLS, ["request_id"], [
            (_int(r[0]), _int(r[1]), _int(r[2]), _int(r[3]), _int(r[4]), _int(r[5]), _int(r[6]), r[7], r[8], r[9],
             r[10], r[11], r[12], r[13], r[14], r[15], _int(r[16]), r[17], r[18]) for r in requests])
        cur.execute(f"DELETE FROM core.sa_conc_request WHERE request_date < now() - interval '{SA_REQUEST_DAYS} days'")
        n += _replace(cur, "core.sa_conc_manager", _MANAGER_COLS, [
            (f"{int(r[0])}|{int(r[1])}", _int(r[0]), _int(r[1]), r[2], r[3], _int(r[4]), _int(r[5]), r[6], r[7],
             r[8], r[9], r[10]) for r in managers])
        n += _replace(cur, "core.sa_wf_notification", _WF_COLS, [
            (_int(r[0]), r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11], r[12], r[13], r[14],
             r[15] == "Y") for r in notifs])
        rows_upserted = n
        new_wm = max((r[18] for r in requests if r[18]), default=None)
        _set_watermark(cur, job, "requests", new_wm)

        run.pg.commit()
        refresh_marts_for_job(job)
        run.finish("success", rows_read, rows_upserted, wm_from=wm, wm_to=new_wm or wm)
    except Exception as e:
        run.pg.rollback()
        logger.error("[%s] failed: %s", job, e)
        run.finish("failed", rows_read, rows_upserted, error=str(e), wm_from=wm)
        run.close()
        raise
    run.close()
    return {"status": "success", "rows_read": rows_read, "rows_upserted": rows_upserted}
