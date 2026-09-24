"""
CKDO EBS Data Tools — the OpenAPI tool server from the blueprint (section 7),
mounted at /api/v1/ebs-tools as its own FastAPI application.

Its own app rather than a router on the dashboard: Open WebUI turns every
operation in the spec it is given into a tool, so the spec must contain the
EBS tools and nothing else — not the few hundred dashboard endpoints. Each
operation_id is the tool name the model sees, and each summary/Field
description is the text it reads to decide when and how to call it.

Register in Open WebUI (Admin Settings -> Tools / Connections):
  URL          https://dashboard.ckd-otto.com/api/v1/ebs-tools
  OpenAPI      openapi.json
  Auth         "Session"/OAuth (forwards the user's Keycloak token — preferred)
               or Bearer <EBS_TOOLS_SERVICE_KEY> with
               ENABLE_FORWARD_USER_INFO_HEADERS=true on Open WebUI, so each
               call carries X-OpenWebUI-User-Email.

Who may read what is decided per call from the caller's ebs-* groups
(access.py), never from which Open WebUI model or tool the call came through.
"""
import hmac
from datetime import date
from typing import Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.dependencies import get_jwks
from app.services.ebs_mart import tools
from app.services.ebs_mart.access import AccessDenied, Caller, normalize_groups, scope_groups
from app.services.ebs_mart.query import QueryFailed
from app.services.ebs_mart.sql_guard import SqlRejected

settings = get_settings()

app = FastAPI(
    title="CKDO EBS Data Tools",
    description=(
        "Akses read-only ke data mart Oracle EBS PT CKD OTTO Pharmaceuticals "
        "(OU org_id 81, ledger 2022 IDR, process org 121). Semua angka berasal dari schema mart.* "
        "yang diisi ETL dari Oracle EBS; setiap hasil membawa as_of (waktu data), sql_used, "
        "row_count dan truncated."
    ),
    version="1.0.0",
    root_path_in_servers=False,
)

# Only relevant when a tool server is added per user in Open WebUI (the
# browser then calls it directly); admin-level connections are called from
# the Open WebUI backend and never send an Origin.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://cochat(-dev)?\.ckd-otto\.com",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(SqlRejected)
async def _rejected(_: Request, e: SqlRejected):
    return JSONResponse(status_code=400, content={"detail": str(e)})


@app.exception_handler(AccessDenied)
async def _denied(_: Request, e: AccessDenied):
    return JSONResponse(status_code=403, content={"detail": str(e)})


@app.exception_handler(QueryFailed)
async def _failed(_: Request, e: QueryFailed):
    return JSONResponse(status_code=422, content={"detail": str(e)})


# ── Identity ─────────────────────────────────────────────────────────────────

def _service_key() -> str:
    return settings.ebs_tools_service_key or settings.ebs_chat_service_key


async def current_caller(
    authorization: Optional[str] = Header(None),
    x_service_key: Optional[str] = Header(None),
    x_user_email: Optional[str] = Header(None),
    x_openwebui_user_email: Optional[str] = Header(None),
    x_openwebui_chat_id: Optional[str] = Header(None),
) -> Caller:
    """Keycloak token (groups claim + ebs_chat_scope) or service key plus a
    forwarded user email (ebs_chat_scope only). The service key alone,
    without an email, identifies no one and is refused: every row this
    server returns is attributed to a person in meta.chat_query_log."""
    bearer = authorization[7:].strip() if authorization and authorization.lower().startswith("bearer ") else None
    key = _service_key()
    presented_key = x_service_key or bearer

    if key and presented_key and hmac.compare_digest(presented_key, key):
        email = (x_openwebui_user_email or x_user_email or "").strip().lower()
        if not email:
            raise HTTPException(401, "Service key diterima, tapi email user tidak diteruskan "
                                     "(aktifkan ENABLE_FORWARD_USER_INFO_HEADERS di Open WebUI).")
        groups = await run_in_threadpool(scope_groups, email)
        return Caller(email=email, groups=groups, source="service-key", chat_id=x_openwebui_chat_id)

    if bearer:
        try:
            jwks = await get_jwks()
            try:
                claims = jwt.decode(bearer, jwks, algorithms=["RS256"], options={"verify_aud": False})
            except JWTError:
                claims = jwt.decode(bearer, await get_jwks(force=True), algorithms=["RS256"],
                                    options={"verify_aud": False})
        except Exception:
            raise HTTPException(401, "Token tidak valid atau kedaluwarsa.")
        email = (claims.get("email") or "").strip().lower()
        token_groups = normalize_groups(claims.get("groups", []))
        # Realm roles named ebs-* count too — some realms model these as
        # roles rather than groups.
        token_groups |= normalize_groups(claims.get("realm_access", {}).get("roles", []))
        groups = token_groups | (await run_in_threadpool(scope_groups, email) if email else set())
        return Caller(email=email, groups=groups, source="keycloak", chat_id=x_openwebui_chat_id)

    raise HTTPException(401, "Butuh token Keycloak (Authorization: Bearer) atau service key + email user.")


def _call(fn, *args, **kwargs):
    return run_in_threadpool(fn, *args, **kwargs)


# ── Request bodies ───────────────────────────────────────────────────────────

class FindIn(BaseModel):
    keywords: str = Field(..., description="Kata kunci bisnis dari pertanyaan user, mis. 'hutang jatuh tempo' atau 'stok expired'")


class SqlIn(BaseModel):
    sql: str = Field(..., description="Tepat satu SELECT PostgreSQL atas tabel mart.* saja (lihat find_marts untuk nama kolom). Tanpa titik koma ganda, tanpa DML/DDL.")
    question: str = Field("", description="Pertanyaan asli user, untuk audit")


class AgingIn(BaseModel):
    supplier: Optional[str] = Field(None, description="Nama supplier (cocok sebagian, tidak peka huruf besar/kecil)")
    min_days_overdue: Optional[int] = Field(None, description="Hanya hutang yang lewat jatuh tempo minimal N hari, mis. 60. Kosongkan untuk semua termasuk yang belum jatuh tempo.")
    currency: Optional[str] = Field(None, description="Kode mata uang invoice, mis. USD. Kosongkan untuk semua.")
    group_by: Literal["supplier", "bucket", "supplier_bucket"] = Field(
        "supplier", description="supplier = satu baris per supplier dengan kolom per bucket (laporan aging standar); bucket = total per bucket; supplier_bucket = baris per supplier × bucket")


class OpenInvoiceIn(BaseModel):
    supplier: Optional[str] = Field(None, description="Nama supplier (cocok sebagian)")
    invoice_num: Optional[str] = Field(None, description="Nomor invoice persis")
    min_days_overdue: Optional[int] = Field(None, description="Minimal hari lewat jatuh tempo")
    due_from: Optional[date] = Field(None, description="Jatuh tempo mulai tanggal (YYYY-MM-DD)")
    due_to: Optional[date] = Field(None, description="Jatuh tempo sampai tanggal (YYYY-MM-DD)")
    currency: Optional[str] = Field(None, description="Kode mata uang invoice")


class PaymentsIn(BaseModel):
    supplier: Optional[str] = Field(None, description="Nama supplier (cocok sebagian)")
    invoice_num: Optional[str] = Field(None, description="Nomor invoice persis")
    payment_number: Optional[str] = Field(None, description="Nomor dokumen pembayaran persis")
    date_from: Optional[date] = Field(None, description="Tanggal bayar mulai (YYYY-MM-DD)")
    date_to: Optional[date] = Field(None, description="Tanggal bayar sampai (YYYY-MM-DD)")
    group_by: Literal["none", "supplier", "month"] = Field("none", description="none = detail per pembayaran; supplier = total per supplier; month = total per bulan")


class HoldsIn(BaseModel):
    supplier: Optional[str] = Field(None, description="Nama supplier (cocok sebagian)")
    hold_code: Optional[str] = Field(None, description="Kode hold (awalan), mis. QTY atau PRICE")


class ExpiringIn(BaseModel):
    days: int = Field(90, description="Lot yang ED-nya dalam N hari ke depan", ge=0, le=3650)
    item: Optional[str] = Field(None, description="Kode item persis ATAU nama bahan/barang (cocok sebagian)")
    subinventory_type: Optional[Literal["GOOD", "REJECT", "QUARANTINE"]] = Field(
        "GOOD", description="Klasifikasi subinventory; default GOOD (stok yang bisa dipakai). null = semua.")
    include_expired: bool = Field(False, description="true untuk ikut menampilkan lot yang sudah lewat ED")


class OnhandIn(BaseModel):
    item: Optional[str] = Field(None, description="Kode item persis ATAU nama bahan/barang (cocok sebagian)")
    subinventory: Optional[str] = Field(None, description="Kode subinventory persis")
    lot_number: Optional[str] = Field(None, description="Nomor lot persis")
    subinventory_type: Optional[Literal["GOOD", "REJECT", "QUARANTINE"]] = Field(None, description="Filter klasifikasi subinventory")
    group_by: Literal["item", "subinventory", "lot"] = Field(
        "item", description="item = total per item dipecah GOOD/QUARANTINE/REJECT; subinventory = per item × subinventory; lot = detail per lot dengan ED")


class MovementIn(BaseModel):
    item: Optional[str] = Field(None, description="Kode item persis ATAU nama barang (cocok sebagian)")
    date_from: Optional[date] = Field(None, description="Tanggal transaksi mulai (YYYY-MM-DD)")
    date_to: Optional[date] = Field(None, description="Tanggal transaksi sampai (YYYY-MM-DD)")
    transaction_type: Optional[str] = Field(None, description="Tipe transaksi (cocok sebagian), mis. Receipt, Issue, Transfer")
    subinventory: Optional[str] = Field(None, description="Kode subinventory persis")
    group_by: Literal["type", "item", "day", "month"] = Field("type", description="Pengelompokan hasil")


# ── Operations ───────────────────────────────────────────────────────────────

@app.post("/find_marts", operation_id="find_marts",
          summary="Cari mart & kolom yang relevan untuk pertanyaan bisnis (panggil ini dulu sebelum run_sql)")
async def find_marts(body: FindIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.find_marts, caller, body.keywords)


@app.post("/run_sql", operation_id="run_sql",
          summary="Jalankan satu SELECT read-only atas schema mart (untuk pertanyaan ad-hoc yang tidak dicakup intent tool)")
async def run_sql(body: SqlIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.run_sql, caller, body.sql, body.question)


@app.post("/get_data_freshness", operation_id="get_data_freshness",
          summary="Daftar mart yang bisa Anda akses, jumlah baris, dan waktu data terakhir (as_of)")
async def get_data_freshness(caller: Caller = Depends(current_caller)):
    return await _call(tools.get_data_freshness, caller)


@app.post("/get_ap_aging", operation_id="get_ap_aging",
          summary="Aging hutang usaha (AP) per supplier dan bucket umur: Current, 1-30, 31-60, 61-90, >90 hari")
async def get_ap_aging(body: AgingIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.get_ap_aging, caller, **body.model_dump())


@app.post("/get_ap_open_invoices", operation_id="get_ap_open_invoices",
          summary="Daftar invoice supplier yang belum lunas, dengan jatuh tempo dan sisa hutang (valas + IDR)")
async def get_ap_open_invoices(body: OpenInvoiceIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.get_ap_open_invoices, caller, **body.model_dump())


@app.post("/get_ap_payments", operation_id="get_ap_payments",
          summary="Riwayat pembayaran ke supplier (per pembayaran, per supplier, atau per bulan)")
async def get_ap_payments(body: PaymentsIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.get_ap_payments, caller, **body.model_dump())


@app.post("/get_ap_holds", operation_id="get_ap_holds",
          summary="Invoice supplier yang sedang di-hold (belum di-release) beserta alasannya")
async def get_ap_holds(body: HoldsIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.get_ap_holds, caller, **body.model_dump())


@app.post("/get_expiring_lots", operation_id="get_expiring_lots",
          summary="Lot persediaan yang akan (atau sudah) kedaluwarsa dalam N hari, dengan qty dan satuan")
async def get_expiring_lots(body: ExpiringIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.get_expiring_lots, caller, **body.model_dump())


@app.post("/get_stock_onhand", operation_id="get_stock_onhand",
          summary="Stok on-hand saat ini per item, per subinventory, atau per lot (org 121)")
async def get_stock_onhand(body: OnhandIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.get_stock_onhand, caller, **body.model_dump())


@app.post("/get_stock_movement", operation_id="get_stock_movement",
          summary="Mutasi stok (masuk/keluar) per tipe transaksi, item, hari, atau bulan")
async def get_stock_movement(body: MovementIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.get_stock_movement, caller, **body.model_dump())


# ── Export (Open WebUI "Export Excel" action) — not a tool, kept out of the spec ──

class ExportIn(BaseModel):
    markdown: str
    title: str = "EBS Analyst"


@app.post("/export/xlsx", include_in_schema=False)
async def export_xlsx(body: ExportIn, caller: Caller = Depends(current_caller)):
    from app.services.ebs_mart.export import build_xlsx
    try:
        token, n = await run_in_threadpool(build_xlsx, body.markdown, body.title)
    except ValueError as e:
        raise HTTPException(400, str(e))
    # Relative: nginx does not forward the scheme, so an absolute URL built
    # here would say http:// behind TLS. The Action prefixes its own
    # dashboard_url valve, which is the address that already worked for it.
    return {"path": f"/api/v1/ebs-tools/export/{token}.xlsx", "tables": n}


@app.get("/export/{token}.xlsx", include_in_schema=False)
async def export_download(token: str):
    from fastapi.responses import FileResponse
    from app.services.ebs_mart.export import export_path
    path = export_path(token)
    if not path:
        raise HTTPException(404, "Link sudah kedaluwarsa atau tidak valid.")
    return FileResponse(path, filename="ebs-analyst.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}
