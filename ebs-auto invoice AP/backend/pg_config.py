import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()


def get_pg_connection():
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "postgres"),
        port=int(os.getenv("PG_PORT", "5432")),
        dbname=os.getenv("PG_DB", "ap_invoice"),
        user=os.getenv("PG_USER", "ap_user"),
        password=os.getenv("PG_PASSWORD", "ap_secret"),
    )
