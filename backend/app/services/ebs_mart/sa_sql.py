"""
System Administration domain (blueprint v2 section 4.7, library v2 3.2b / 13b):
core tables, SoD rules and the twelve mart.sa_* definitions.

Kept apart from mart_sql.py because the whole domain is fenced off: its
marts are granted to llm_sa_ro only (schema.grant_sa_reader), never to
llm_ro/chat_readonly, and only the SYSADMIN_ALLOWLIST emails reach them
(access.py). mart_sql.py merges the definitions below into its registries so
creation, refresh and cataloguing work the same as every other mart.

What is never extracted (blueprint "Aturan khusus ETL domain ini"):
FND_USER.ENCRYPTED_FOUNDATION_PASSWORD / ENCRYPTED_USER_PASSWORD, and profile
options whose name reads like a password or credential (_PROFILE_BLACKLIST,
applied in the Oracle WHERE clause and again in Python before insert).
"""

# Profile option names (internal or user name) that are never pulled.
# Deliberately broad: a harmless profile lost to it costs less than one
# credential that gets through.
PROFILE_BLACKLIST_REGEX = "PASSWORD|PASSWD|PWD|SECRET|TOKEN|CREDENTIAL|WALLET|PRIVATE.?KEY|API.?KEY|ENCRYPT|SIGNON.?PASS"

# Seeded (Oracle-delivered) accounts: SYSADMIN, GUEST, AUTOINSTALL,
# ANONYMOUS, the integration/interface users. Custom accounts start at
# user_id 1000 on R12, and seeded rows are created by AUTOINSTALL (1) or
# ANONYMOUS (2) — never by a person, so a user an administrator created
# while signed in as SYSADMIN (created_by 0) is not caught here.
_SEEDED = "(u.user_id < 1000 OR u.created_by IN (1, 2))"

# Today in EBS's clock. Oracle stores WIB wall-clock times while this
# PostgreSQL runs in UTC, so CURRENT_DATE is yesterday until 07:00 WIB.
TODAY = "(now() AT TIME ZONE 'Asia/Jakarta')::date"


# "Aktif" as the blueprint defines it: end_date empty or after today.
def _active(alias: str) -> str:
    return (f"(({alias}.start_date IS NULL OR {alias}.start_date <= {TODAY}) "
            f"AND ({alias}.end_date IS NULL OR {alias}.end_date > {TODAY}))")


SA_META_DDL = [
    # Segregation-of-duties rules. function_a / function_b are LIKE patterns
    # on FND function_name (the internal code, e.g. AP_APXINWKB%); a rule is
    # violated by an active user who reaches at least one function on each
    # side, through any of their active responsibilities. Several rows may
    # share a rule_name to list more functions for the same conflict.
    """
    CREATE TABLE IF NOT EXISTS meta.sod_rules (
        rule_id      serial PRIMARY KEY,
        rule_name    text NOT NULL,
        function_a   text NOT NULL,
        function_b   text NOT NULL,
        risk         text NOT NULL DEFAULT 'High',
        description  text,
        enabled      boolean NOT NULL DEFAULT true,
        created_by   text,
        created_at   timestamptz DEFAULT now(),
        UNIQUE (rule_name, function_a, function_b)
    )
    """,
]

# Blueprint v2's examples: supplier maintenance vs payment, PO entry vs
# receiving, AR invoice vs receipt, user administration vs financial
# transactions — plus AP invoice vs payment and GL journal entry vs posting,
# the classic pairs auditors ask for first. Patterns name the ENTRY
# functions exactly (found in this instance's FND_FORM_FUNCTIONS on the first
# run, 2026-09-28): a broad AR_ARXTWMAI% would also catch "Invoice: View" and
# flag every inquiry-only user. Seed rows are replaced on every startup; rows
# added by hand (created_by <> 'seed') stay.
_SUPPLIER_EDIT = ("AP_APXVDMVD", "POS_HT_SP_B_ORG_CRT", "POS_HT_SP_B_PAY")
SOD_SEED = [
    *[("Supplier master vs pembayaran", a, "AP_APXPAWKB", "High",
       "Bisa membuat/mengubah supplier (termasuk rekening bank) sekaligus membuat pembayaran.")
      for a in _SUPPLIER_EDIT],
    ("Invoice AP vs pembayaran", "AP_APXINWKB", "AP_APXPAWKB", "High",
     "Bisa memasukkan invoice supplier sekaligus membayarnya."),
    ("PO vs penerimaan barang", "PO_POXPOEPO", "RCV_RCVRCERC", "High",
     "Bisa membuat PO sekaligus mencatat penerimaan barangnya."),
    ("Invoice AR vs receipt", "AR_ARXTWMAI_INVOICES_ENTER", "AR_ARXRWMAI_CASH_ENTER", "Medium",
     "Bisa membuat invoice customer sekaligus mencatat penerimaan kasnya."),
    ("Jurnal GL: buat vs posting", "GLXJEENT_A", "GLXJEPST", "Medium",
     "Bisa membuat jurnal GL sekaligus mem-posting-nya sendiri."),
    *[("Administrasi user vs transaksi keuangan", "FND_FNDSCAUS", b, "Critical",
       "Bisa membuat user/memberi responsibility sekaligus menjalankan transaksi keuangan.")
      for b in ("AP_APXINWKB", "AP_APXPAWKB", "GLXJEENT_A", "AR_ARXRWMAI_CASH_ENTER")],
]

RISK_ORDER = "CASE risk WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 ELSE 4 END"

SA_CORE_DDL = [
    """
    CREATE TABLE IF NOT EXISTS core.sa_user (
        user_id               bigint PRIMARY KEY,
        user_name             text,
        description           text,
        email_address         text,
        start_date            date,
        end_date              date,
        last_logon_date       timestamp,
        password_date         date,
        employee_id           bigint,
        employee_number       text,
        employee_name         text,
        current_employee_flag text,
        termination_date      date,
        created_by            bigint,
        creation_date         timestamp,
        loaded_at             timestamptz DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.sa_resp (
        resp_id              bigint,
        app_id               bigint,
        app_short_name       text,
        resp_key             text,
        resp_name            text,
        description          text,
        menu_id              bigint,
        request_group_id     bigint,
        group_application_id bigint,
        start_date           date,
        end_date             date,
        version              text,
        loaded_at            timestamptz DEFAULT now(),
        PRIMARY KEY (resp_id, app_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.sa_user_resp (
        row_key           text PRIMARY KEY,
        user_id           bigint,
        resp_id           bigint,
        app_id            bigint,
        security_group_id bigint,
        grant_type        text,
        start_date        date,
        end_date          date,
        loaded_at         timestamptz DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_core_sa_user_resp_user ON core.sa_user_resp (user_id)",
    "CREATE INDEX IF NOT EXISTS idx_core_sa_user_resp_resp ON core.sa_user_resp (resp_id, app_id)",
    """
    CREATE TABLE IF NOT EXISTS core.sa_menu (
        menu_id        bigint PRIMARY KEY,
        menu_name      text,
        user_menu_name text,
        loaded_at      timestamptz DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.sa_function (
        function_id        bigint PRIMARY KEY,
        function_name      text,
        user_function_name text,
        function_type      text,
        description        text,
        loaded_at          timestamptz DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.sa_menu_function (
        menu_id     bigint,
        function_id bigint,
        PRIMARY KEY (menu_id, function_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_core_sa_menu_function_fn ON core.sa_menu_function (function_id)",
    """
    CREATE TABLE IF NOT EXISTS core.sa_resp_exclusion (
        resp_id   bigint,
        app_id    bigint,
        rule_type text,
        action_id bigint,
        PRIMARY KEY (resp_id, app_id, rule_type, action_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.sa_application (
        app_id     bigint PRIMARY KEY,
        short_name text,
        name       text
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.sa_conc_program (
        program_id         bigint,
        app_id             bigint,
        program_short_name text,
        program_name       text,
        enabled_flag       text,
        PRIMARY KEY (program_id, app_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.sa_request_set (
        set_id         bigint,
        app_id         bigint,
        set_short_name text,
        set_name       text,
        PRIMARY KEY (set_id, app_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.sa_request_group_unit (
        row_key            text PRIMARY KEY,
        request_group_id   bigint,
        rg_app_id          bigint,
        request_group_name text,
        unit_type          text,
        unit_id            bigint,
        unit_app_id        bigint
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.sa_profile_value (
        row_key            text PRIMARY KEY,
        profile_option_id  bigint,
        profile_app_id     bigint,
        profile_name       text,
        user_profile_name  text,
        level_id           int,
        level_value        bigint,
        level_value_app_id bigint,
        level_value_name   text,
        value              text,
        value_display      text,
        last_update_date   timestamp,
        loaded_at          timestamptz DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.sa_login (
        row_key        text PRIMARY KEY,
        login_id       bigint,
        user_id        bigint,
        login_start    timestamp,
        login_end      timestamp,
        login_type     text,
        terminal_id    text,
        login_resp_id  bigint,
        resp_id        bigint,
        resp_app_id    bigint,
        resp_start     timestamp,
        resp_end       timestamp,
        form_id        bigint,
        form_app_id    bigint,
        form_name      text,
        user_form_name text,
        form_start     timestamp,
        form_end       timestamp,
        loaded_at      timestamptz DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_core_sa_login_start ON core.sa_login (login_start)",
    """
    CREATE TABLE IF NOT EXISTS core.sa_conc_request (
        request_id             bigint PRIMARY KEY,
        parent_request_id      bigint,
        program_id             bigint,
        program_app_id         bigint,
        requested_by           bigint,
        resp_id                bigint,
        resp_app_id            bigint,
        phase_code             text,
        status_code            text,
        request_date           timestamp,
        requested_start_date   timestamp,
        actual_start_date      timestamp,
        actual_completion_date timestamp,
        completion_text        text,
        argument_text          text,
        hold_flag              text,
        priority               int,
        queue_name             text,
        src_last_update        timestamp,
        loaded_at              timestamptz DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_core_sa_conc_request_date ON core.sa_conc_request (request_date)",
    """
    CREATE TABLE IF NOT EXISTS core.sa_conc_manager (
        queue_key         text PRIMARY KEY,
        queue_id          bigint,
        app_id            bigint,
        queue_short_name  text,
        manager_name      text,
        max_processes     int,
        running_processes int,
        enabled_flag      text,
        control_code      text,
        control_meaning   text,
        target_node       text,
        manager_type      text,
        loaded_at         timestamptz DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.sa_wf_notification (
        notification_id    bigint PRIMARY KEY,
        item_type          text,
        item_type_name     text,
        message_name       text,
        recipient_role     text,
        recipient_name     text,
        original_recipient text,
        from_user          text,
        more_info_role     text,
        mail_status        text,
        begin_date         timestamp,
        due_date           timestamp,
        subject            text,
        item_key           text,
        user_key           text,
        requires_response  boolean,
        loaded_at          timestamptz DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.sa_patch (
        row_key                text PRIMARY KEY,
        bug_id                 bigint,
        bug_number             text,
        application_short_name text,
        applied_date           timestamp,
        last_update_date       timestamp,
        language               text,
        aru_release_name       text,
        trackable_entity       text,
        baseline_name          text,
        loaded_at              timestamptz DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.sa_form_rule (
        rule_id          bigint PRIMARY KEY,
        function_name    text,
        form_name        text,
        sequence         numeric,
        description      text,
        rule_type        text,
        enabled          text,
        trigger_event    text,
        trigger_object   text,
        condition_text   text,
        actions_enabled  int,
        last_update_date timestamp,
        last_updated_by  bigint,
        loaded_at        timestamptz DEFAULT now()
    )
    """,
]

_PHASE = """CASE {c}.phase_code WHEN 'C' THEN 'Completed' WHEN 'I' THEN 'Inactive' WHEN 'P' THEN 'Pending'
                     WHEN 'R' THEN 'Running' ELSE {c}.phase_code END"""
_STATUS = """CASE {c}.status_code WHEN 'A' THEN 'Waiting' WHEN 'B' THEN 'Resuming' WHEN 'C' THEN 'Normal'
                     WHEN 'D' THEN 'Cancelled' WHEN 'E' THEN 'Error' WHEN 'F' THEN 'Scheduled' WHEN 'G' THEN 'Warning'
                     WHEN 'H' THEN 'On Hold' WHEN 'I' THEN 'Normal' WHEN 'M' THEN 'No Manager' WHEN 'P' THEN 'Scheduled'
                     WHEN 'Q' THEN 'Standby' WHEN 'R' THEN 'Normal' WHEN 'S' THEN 'Suspended' WHEN 'T' THEN 'Terminating'
                     WHEN 'U' THEN 'Disabled' WHEN 'W' THEN 'Paused' WHEN 'X' THEN 'Terminated' WHEN 'Z' THEN 'Waiting'
                     ELSE {c}.status_code END"""

# Responsibilities anyone was ever given. The function and request-group
# marts are limited to these: the ~thousands of seeded responsibilities
# nobody holds would multiply the rows without answering any question.
_ASSIGNED = "EXISTS (SELECT 1 FROM core.sa_user_resp x WHERE x.resp_id = r.resp_id AND x.app_id = r.app_id)"
# How many active users hold it right now (active user, active assignment):
# the tools default to responsibilities someone actually uses, not the
# seeded ones a retired account still carries.
_HOLDERS = f"""LEFT JOIN (SELECT ur.resp_id, ur.app_id, COUNT(DISTINCT ur.user_id) AS n
                     FROM core.sa_user_resp ur JOIN core.sa_user u ON u.user_id = ur.user_id
                    WHERE {_active('u')} AND {_active('ur')}
                    GROUP BY ur.resp_id, ur.app_id) h ON h.resp_id = r.resp_id AND h.app_id = r.app_id"""

# Order matters: sa_user reads mart.sa_user_resp, and sa_sod_violation reads
# sa_user_resp and sa_resp_function, so those are created (and refreshed)
# first. ensure_marts recreates a dependent that a CASCADE drop removed.
SA_MART_SQL: dict[str, str] = {
    "sa_user_resp": f"""
        SELECT ur.row_key,
               ur.user_id,
               u.user_name,
               u.employee_name,
               {_SEEDED}                                          AS is_seeded,
               {_active('u')}                                     AS is_user_active,
               ur.resp_id                                         AS responsibility_id,
               ur.app_id                                          AS application_id,
               r.app_short_name,
               r.resp_name                                        AS responsibility_name,
               r.resp_key                                         AS responsibility_key,
               ur.grant_type,
               ur.start_date,
               ur.end_date,
               {_active('ur')}                                    AS is_assignment_active,
               (r.resp_id IS NOT NULL AND {_active('r')})         AS is_resp_active,
               ({_active('u')} AND {_active('ur')} AND r.resp_id IS NOT NULL AND {_active('r')}) AS is_active
          FROM core.sa_user_resp ur
          JOIN core.sa_user u      ON u.user_id = ur.user_id
          LEFT JOIN core.sa_resp r ON r.resp_id = ur.resp_id AND r.app_id = ur.app_id
    """,

    "sa_user": f"""
        SELECT u.user_id,
               u.user_name,
               u.description,
               u.email_address,
               u.start_date,
               u.end_date,
               {_active('u')}                                     AS is_active,
               u.last_logon_date,
               {TODAY} - u.last_logon_date::date             AS days_since_login,
               u.last_logon_date IS NULL                          AS never_logged_in,
               u.password_date,
               u.employee_id,
               u.employee_number,
               u.employee_name,
               CASE WHEN u.employee_id IS NULL THEN 'Tanpa karyawan'
                    WHEN u.current_employee_flag = 'Y' THEN 'Aktif'
                    WHEN u.termination_date IS NOT NULL AND u.termination_date <= {TODAY} THEN 'Keluar'
                    ELSE 'Tidak aktif' END                        AS employee_status,
               u.termination_date,
               {_SEEDED}                                          AS is_seeded,
               COALESCE(a.n, 0)                                   AS active_resp_count
          FROM core.sa_user u
          LEFT JOIN (SELECT user_id, COUNT(*) AS n FROM mart.sa_user_resp WHERE is_active GROUP BY user_id) a
                 ON a.user_id = u.user_id
    """,

    # Functions a responsibility reaches: FND_COMPILED_MENU_FUNCTIONS of its
    # menu (EBS's own flattened, grant-checked menu tree), minus function
    # exclusions (rule_type F) and minus every function of an excluded menu
    # (rule_type M, via that menu's compiled set). The M rule is slightly
    # stricter than FND_FUNCTION.TEST when the same function is also reached
    # through a second, non-excluded submenu — rare, and it only ever hides
    # access, never invents it.
    "sa_resp_function": f"""
        SELECT MD5(CONCAT_WS('|', r.resp_id, r.app_id, f.function_id)) AS row_key,
               r.resp_id                                         AS responsibility_id,
               r.app_id                                          AS application_id,
               r.resp_name                                       AS responsibility_name,
               r.app_short_name,
               m.user_menu_name                                  AS menu_name,
               f.function_id,
               f.function_name,
               f.user_function_name,
               f.function_type,
               {_active('r')}                                    AS is_resp_active,
               COALESCE(h.n, 0)                                  AS active_holders
          FROM core.sa_resp r
          JOIN core.sa_menu_function mf ON mf.menu_id = r.menu_id
          JOIN core.sa_function f       ON f.function_id = mf.function_id
          LEFT JOIN core.sa_menu m      ON m.menu_id = r.menu_id
          {_HOLDERS}
         WHERE {_ASSIGNED}
           AND NOT EXISTS (SELECT 1 FROM core.sa_resp_exclusion x
                            WHERE x.resp_id = r.resp_id AND x.app_id = r.app_id
                              AND x.rule_type = 'F' AND x.action_id = f.function_id)
           AND NOT EXISTS (SELECT 1 FROM core.sa_resp_exclusion x
                             JOIN core.sa_menu_function xm ON xm.menu_id = x.action_id
                            WHERE x.resp_id = r.resp_id AND x.app_id = r.app_id
                              AND x.rule_type = 'M' AND xm.function_id = f.function_id)
    """,

    "sa_resp_request_group": f"""
        SELECT MD5(CONCAT_WS('|', r.resp_id, r.app_id, u.row_key))  AS row_key,
               r.resp_id                                          AS responsibility_id,
               r.app_id                                           AS application_id,
               r.resp_name                                        AS responsibility_name,
               r.app_short_name,
               u.request_group_name,
               CASE u.unit_type WHEN 'P' THEN 'Program' WHEN 'S' THEN 'Request Set'
                                WHEN 'A' THEN 'Semua program aplikasi' ELSE u.unit_type END AS unit_type,
               ua.short_name                                      AS unit_app_short_name,
               CASE u.unit_type WHEN 'P' THEN p.program_short_name WHEN 'S' THEN rs.set_short_name
                                WHEN 'A' THEN ua.short_name END   AS unit_short_name,
               CASE u.unit_type WHEN 'P' THEN p.program_name WHEN 'S' THEN rs.set_name
                                WHEN 'A' THEN 'Semua program ' || COALESCE(ua.name, ua.short_name) END AS unit_name,
               p.enabled_flag                                     AS program_enabled,
               {_active('r')}                                     AS is_resp_active,
               COALESCE(h.n, 0)                                   AS active_holders
          FROM core.sa_resp r
          JOIN core.sa_request_group_unit u ON u.request_group_id = r.request_group_id
                                           AND u.rg_app_id = r.group_application_id
          LEFT JOIN core.sa_conc_program p  ON u.unit_type = 'P' AND p.program_id = u.unit_id AND p.app_id = u.unit_app_id
          LEFT JOIN core.sa_request_set rs  ON u.unit_type = 'S' AND rs.set_id = u.unit_id AND rs.app_id = u.unit_app_id
          LEFT JOIN core.sa_application ua  ON ua.app_id = u.unit_app_id
          {_HOLDERS}
         WHERE {_ASSIGNED}
    """,

    # precedence: the order FND resolves a value in — User wins over
    # Responsibility over Application over Site. Server / Organization
    # levels sit outside that chain and are listed last.
    "sa_profile_value": """
        SELECT p.row_key,
               p.profile_name                                     AS profile_option_name,
               p.user_profile_name,
               p.level_id,
               CASE p.level_id WHEN 10001 THEN 'Site' WHEN 10002 THEN 'Application' WHEN 10003 THEN 'Responsibility'
                               WHEN 10004 THEN 'User' WHEN 10005 THEN 'Server' WHEN 10006 THEN 'Organization'
                               WHEN 10007 THEN 'Server+Responsibility' ELSE p.level_id::text END AS level_name,
               CASE p.level_id WHEN 10004 THEN 1 WHEN 10003 THEN 2 WHEN 10002 THEN 3 WHEN 10001 THEN 4 ELSE 5 END
                                                                  AS precedence,
               p.level_value,
               p.level_value_app_id,
               p.level_value_name,
               p.value,
               p.value_display,
               p.last_update_date
          FROM core.sa_profile_value p
    """,

    "sa_login_audit": f"""
        SELECT l.row_key,
               l.login_id,
               l.user_id,
               u.user_name,
               u.employee_name,
               l.login_start,
               l.login_end,
               ROUND(EXTRACT(EPOCH FROM (l.login_end - l.login_start)) / 60)::int AS login_minutes,
               l.login_type,
               l.terminal_id,
               r.resp_name                                        AS responsibility_name,
               l.resp_start,
               l.resp_end,
               l.form_name,
               l.user_form_name,
               l.form_start,
               l.form_end
          FROM core.sa_login l
          LEFT JOIN core.sa_user u ON u.user_id = l.user_id
          LEFT JOIN core.sa_resp r ON r.resp_id = l.resp_id AND r.app_id = l.resp_app_id
         WHERE l.login_start >= {TODAY} - 90
    """,

    # run_minutes only for finished requests: Oracle stores local time and
    # the refresh clock's zone is not guaranteed to match, so "running for N
    # minutes" is left to the tool, which shows actual_start_date instead.
    "sa_concurrent_request": f"""
        SELECT c.request_id,
               c.parent_request_id,
               p.program_short_name,
               COALESCE(p.program_name, 'Program #' || c.program_id) AS program_name,
               a.short_name                                       AS app_short_name,
               u.user_name                                        AS requested_by,
               u.employee_name,
               r.resp_name                                        AS responsibility_name,
               {_PHASE.format(c='c')}                             AS phase,
               {_STATUS.format(c='c')}                            AS status,
               c.phase_code,
               c.status_code,
               c.request_date,
               c.requested_start_date,
               c.actual_start_date,
               c.actual_completion_date,
               ROUND((EXTRACT(EPOCH FROM (c.actual_completion_date - c.actual_start_date)) / 60)::numeric, 1)
                                                                  AS run_minutes,
               ROUND((EXTRACT(EPOCH FROM (c.actual_start_date - GREATEST(c.request_date, c.requested_start_date))) / 60)::numeric, 1)
                                                                  AS wait_minutes,
               c.completion_text,
               c.argument_text,
               c.queue_name,
               c.hold_flag,
               c.priority
          FROM core.sa_conc_request c
          LEFT JOIN core.sa_conc_program p ON p.program_id = c.program_id AND p.app_id = c.program_app_id
          LEFT JOIN core.sa_application a  ON a.app_id = c.program_app_id
          LEFT JOIN core.sa_user u         ON u.user_id = c.requested_by
          LEFT JOIN core.sa_resp r         ON r.resp_id = c.resp_id AND r.app_id = c.resp_app_id
    """,

    "sa_concurrent_manager": """
        SELECT m.queue_key,
               m.queue_id,
               m.app_id,
               m.queue_short_name,
               m.manager_name,
               m.max_processes                                    AS target_processes,
               m.running_processes                                AS actual_processes,
               m.enabled_flag,
               m.control_code,
               m.control_meaning,
               CASE WHEN COALESCE(m.enabled_flag, 'Y') <> 'Y'                   THEN 'Disabled'
                    WHEN COALESCE(m.max_processes, 0) = 0                        THEN 'Nonaktif (target 0)'
                    WHEN COALESCE(m.running_processes, 0) = 0                    THEN 'Down (0 proses)'
                    WHEN m.running_processes < m.max_processes                  THEN 'Kurang proses'
                    ELSE 'Normal' END                             AS status_label,
               m.target_node,
               m.manager_type,
               COALESCE(q.n, 0)                                   AS running_requests
          FROM core.sa_conc_manager m
          LEFT JOIN (SELECT queue_name, COUNT(*) AS n FROM core.sa_conc_request
                      WHERE phase_code = 'R' GROUP BY queue_name) q ON q.queue_name = m.manager_name
    """,

    "sa_wf_open_notification": f"""
        SELECT n.notification_id,
               n.item_type,
               n.item_type_name,
               n.message_name,
               n.recipient_role,
               n.recipient_name,
               n.original_recipient,
               n.from_user,
               n.more_info_role,
               n.subject,
               n.begin_date,
               n.due_date,
               {TODAY} - n.begin_date::date                       AS days_open,
               n.requires_response,
               n.item_key,
               n.user_key,
               n.mail_status
          FROM core.sa_wf_notification n
    """,

    "sa_sod_violation": f"""
        WITH ua AS (
            SELECT user_id, user_name, employee_name, is_seeded, responsibility_id, application_id,
                   responsibility_name, grant_type
              FROM mart.sa_user_resp WHERE is_active
        ), hits AS (
            SELECT s.rule_id, s.rule_name, s.risk, s.description, s.side, ua.user_id, ua.user_name,
                   ua.employee_name, ua.is_seeded, ua.responsibility_name, f.user_function_name, f.function_name
              FROM (SELECT rule_id, rule_name, risk, description, 'A' AS side, function_a AS pattern
                      FROM meta.sod_rules WHERE enabled
                    UNION ALL
                    SELECT rule_id, rule_name, risk, description, 'B', function_b
                      FROM meta.sod_rules WHERE enabled) s
              JOIN mart.sa_resp_function f ON f.function_name LIKE s.pattern
              JOIN ua ON ua.responsibility_id = f.responsibility_id AND ua.application_id = f.application_id
        )
        SELECT MD5(CONCAT_WS('|', user_id, rule_name))                                     AS row_key,
               user_id,
               user_name,
               employee_name,
               is_seeded,
               rule_name,
               MIN(risk)                                                                   AS risk,
               MIN({RISK_ORDER})                                                           AS risk_order,
               MIN(description)                                                            AS description,
               STRING_AGG(DISTINCT COALESCE(user_function_name, function_name), '; ') FILTER (WHERE side = 'A') AS functions_a,
               STRING_AGG(DISTINCT responsibility_name, '; ') FILTER (WHERE side = 'A')    AS responsibilities_a,
               STRING_AGG(DISTINCT COALESCE(user_function_name, function_name), '; ') FILTER (WHERE side = 'B') AS functions_b,
               STRING_AGG(DISTINCT responsibility_name, '; ') FILTER (WHERE side = 'B')    AS responsibilities_b
          FROM hits
         GROUP BY user_id, user_name, employee_name, is_seeded, rule_name
        HAVING BOOL_OR(side = 'A') AND BOOL_OR(side = 'B')
    """,

    "sa_patch": """
        SELECT row_key, bug_number, application_short_name, applied_date, last_update_date, language,
               aru_release_name, trackable_entity, baseline_name
          FROM core.sa_patch
    """,

    "sa_form_personalization": """
        SELECT fr.rule_id,
               fr.form_name,
               fr.function_name,
               fr.sequence,
               fr.description,
               CASE fr.rule_type WHEN 'F' THEN 'Function' WHEN 'A' THEN 'Form' ELSE fr.rule_type END AS rule_level,
               fr.trigger_event,
               fr.trigger_object,
               fr.condition_text,
               fr.actions_enabled,
               fr.last_update_date,
               u.user_name                                        AS last_updated_by
          FROM core.sa_form_rule fr
          LEFT JOIN core.sa_user u ON u.user_id = fr.last_updated_by
         WHERE fr.enabled = 'Y'
    """,
}

SA_UNIQUE_INDEX: dict[str, list[str]] = {
    "sa_user_resp": ["row_key"],
    "sa_user": ["user_id"],
    "sa_resp_function": ["row_key"],
    "sa_resp_request_group": ["row_key"],
    "sa_profile_value": ["row_key"],
    "sa_login_audit": ["row_key"],
    "sa_concurrent_request": ["request_id"],
    "sa_concurrent_manager": ["queue_key"],
    "sa_wf_open_notification": ["notification_id"],
    "sa_sod_violation": ["row_key"],
    "sa_patch": ["row_key"],
    "sa_form_personalization": ["rule_id"],
}

SA_EXTRA_INDEXES: dict[str, list[str]] = {
    "sa_user_resp": ["user_name", "responsibility_name"],
    "sa_user": ["user_name"],
    "sa_resp_function": ["responsibility_name", "function_name"],
    "sa_resp_request_group": ["responsibility_name", "unit_short_name"],
    "sa_profile_value": ["profile_option_name"],
    "sa_login_audit": ["user_name", "login_start"],
    "sa_concurrent_request": ["program_short_name", "request_date", "status_code"],
    "sa_wf_open_notification": ["recipient_role", "item_type"],
    "sa_sod_violation": ["user_name"],
    "sa_patch": ["bug_number"],
    "sa_form_personalization": ["form_name"],
}

# The daily job feeds everything; the 10-minute job only the operational
# three. Dependents follow what they read (see SA_MART_SQL's order note).
SA_MARTS_BY_JOB: dict[str, list[str]] = {
    "etl_mart_sa": ["sa_user_resp", "sa_user", "sa_resp_function", "sa_resp_request_group", "sa_profile_value",
                    "sa_login_audit", "sa_concurrent_request", "sa_sod_violation", "sa_patch",
                    "sa_form_personalization"],
    "etl_mart_sa_ops": ["sa_concurrent_request", "sa_concurrent_manager", "sa_wf_open_notification"],
}
