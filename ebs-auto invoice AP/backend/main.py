from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import upload, invoices, process, debug

app = FastAPI(
    title="CKDO AP Invoice Import",
    description="Import AP Invoice dari PDF Supplier ke Oracle EBS 12.2.8",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router)
app.include_router(invoices.router)
app.include_router(process.router)
app.include_router(debug.router)


@app.get("/health")
def health_check():
    result = {}

    # PostgreSQL check
    try:
        from pg_config import get_pg_connection
        pg = get_pg_connection()
        with pg.cursor() as cur:
            cur.execute("SELECT NOW()")
            result["postgres"] = {"status": "OK", "time": str(cur.fetchone()[0])}
        pg.close()
    except Exception as e:
        result["postgres"] = {"status": "ERROR", "detail": str(e)}

    # Oracle check
    try:
        from config import get_oracle_connection
        ora = get_oracle_connection()
        with ora.cursor() as cur:
            cur.execute("SELECT SYSDATE FROM DUAL")
            result["oracle"] = {"status": "OK", "sysdate": str(cur.fetchone()[0])}
        ora.close()
    except Exception as e:
        result["oracle"] = {"status": "ERROR", "detail": str(e)}

    return result
