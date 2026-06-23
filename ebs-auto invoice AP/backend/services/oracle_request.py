"""
oracle_request.py
Submit concurrent program APXIIMPT (Payables Open Interface Import)

Parameter sesuai form Submit Request EBS (CKDO):
  arg1  = Operating Unit (ORG_ID)
  arg2  = Source
  arg3  = Group           (NULL = semua)
  arg4  = Batch Name      (NULL = semua)
  arg5  = Hold Name       (NULL = no hold)
  arg6  = Hold Reason     (NULL)
  arg7  = GL Date         (NULL = dari interface record)
  arg8  = Purge           (N)
  arg9  = Summarize Report(N)
"""

import oracledb
from config import EBS_USER_ID, EBS_RESP_ID, EBS_RESP_APPL_ID, EBS_ORG_ID, EBS_SOURCE


def submit_apxiimpt(conn: oracledb.Connection) -> int:
    plsql = """
        DECLARE
            v_req_id NUMBER := 0;
        BEGIN
            FND_GLOBAL.APPS_INITIALIZE(
                user_id      => :user_id,
                resp_id      => :resp_id,
                resp_appl_id => :resp_appl_id
            );

            MO_GLOBAL.SET_POLICY_CONTEXT('S', :org_id);

            v_req_id := FND_REQUEST.SUBMIT_REQUEST(
                application => 'SQLAP',
                program     => 'APXIIMPT',
                description => NULL,
                start_time  => NULL,
                sub_request => FALSE,
                argument1   => TO_CHAR(:org_id),
                argument2   => :source,
                argument3   => NULL,
                argument4   => NULL,
                argument5   => NULL,
                argument6   => NULL,
                argument7   => NULL,
                argument8   => 'N',
                argument9   => 'N'
            );

            COMMIT;
            :req_id := v_req_id;
        END;
    """
    req_id_var = conn.cursor().var(int)

    with conn.cursor() as cur:
        cur.execute(plsql, {
            "user_id":      EBS_USER_ID,
            "resp_id":      EBS_RESP_ID,
            "resp_appl_id": EBS_RESP_APPL_ID,
            "org_id":       EBS_ORG_ID,
            "source":       EBS_SOURCE,
            "req_id":       req_id_var,
        })

    req_id = req_id_var.getvalue()

    if not req_id or req_id == 0:
        raise RuntimeError(
            "FND_REQUEST.SUBMIT_REQUEST mengembalikan 0. "
            "Cek FND_USER session atau Payables responsibility."
        )

    conn.commit()
    return req_id


def check_request_status(conn: oracledb.Connection, request_id: int) -> dict:
    sql = """
        SELECT fcr.phase_code,
               fcr.status_code,
               fcr.completion_text,
               fpl.meaning  AS phase_meaning,
               fsl.meaning  AS status_meaning
        FROM   fnd_concurrent_requests   fcr
        JOIN   fnd_lookups               fpl
               ON fpl.lookup_type = 'CP_PHASE_CODE'
              AND fpl.lookup_code = fcr.phase_code
        JOIN   fnd_lookups               fsl
               ON fsl.lookup_type = 'CP_STATUS_CODE'
              AND fsl.lookup_code = fcr.status_code
        WHERE  fcr.request_id = :request_id
    """
    with conn.cursor() as cur:
        cur.execute(sql, {"request_id": request_id})
        row = cur.fetchone()

    if not row:
        return {"phase": "UNKNOWN", "status": "UNKNOWN", "completion_text": None}

    return {
        "phase":           row[3],
        "status":          row[4],
        "phase_code":      row[0],
        "status_code":     row[1],
        "completion_text": row[2],
    }
