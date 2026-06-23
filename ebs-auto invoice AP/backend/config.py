import oracledb
from dotenv import load_dotenv
import os

load_dotenv()

oracledb.init_oracle_client(lib_dir=os.getenv("ORACLE_INSTANT_CLIENT", "/opt/oracle/instantclient"))

# EBS Constants
EBS_USER_ID      = int(os.getenv("EBS_USER_ID", "1110"))
EBS_RESP_ID      = int(os.getenv("EBS_RESP_ID", "50738"))
EBS_RESP_APPL_ID = int(os.getenv("EBS_RESP_APPL_ID", "200"))
EBS_ORG_ID       = int(os.getenv("EBS_ORG_ID", "81"))
EBS_SOURCE       = os.getenv("EBS_SOURCE", "XXCKD_PDF_IMPORT")

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def get_oracle_connection() -> oracledb.Connection:
    """Oracle EBS connection — READ-ONLY kecuali AP Interface insert saat submit."""
    return oracledb.connect(
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        dsn=os.getenv("DB_DSN"),
    )
