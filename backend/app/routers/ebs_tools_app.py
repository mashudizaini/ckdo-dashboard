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


_CATEGORY_DESC = (
    "Kategori item (category set CKDO Inventory), satu atau lebih, nilai persis: API, EXCIPIENT, PRIMER, "
    "SEKUNDER, LIQUID, LYOPHILLIZED, NA. 'Bahan baku' = [API, EXCIPIENT]; 'bahan kemas' = [PRIMER, SEKUNDER]. "
    "Kosongkan untuk semua kategori."
)


class ExpiringIn(BaseModel):
    days: int = Field(90, description="Lot yang ED-nya dalam N hari ke depan", ge=0, le=3650)
    item: Optional[str] = Field(None, description="Kode item persis ATAU nama bahan/barang (cocok sebagian)")
    subinventory_type: Optional[Literal["GOOD", "REJECT", "QUARANTINE"]] = Field(
        "GOOD", description="Klasifikasi subinventory; default GOOD (stok yang bisa dipakai). null = semua.")
    include_expired: bool = Field(False, description="true untuk ikut menampilkan lot yang sudah lewat ED")
    item_category: Optional[list[str]] = Field(None, description=_CATEGORY_DESC)


class OnhandIn(BaseModel):
    item: Optional[str] = Field(None, description="Kode item persis ATAU nama bahan/barang (cocok sebagian)")
    subinventory: Optional[str] = Field(None, description="Kode subinventory persis")
    lot_number: Optional[str] = Field(None, description="Nomor lot persis")
    subinventory_type: Optional[Literal["GOOD", "REJECT", "QUARANTINE"]] = Field(None, description="Filter klasifikasi subinventory")
    group_by: Literal["item", "subinventory", "lot"] = Field(
        "item", description="item = total per item dipecah GOOD/QUARANTINE/REJECT; subinventory = per item × subinventory; lot = detail per lot dengan ED")
    item_category: Optional[list[str]] = Field(None, description=_CATEGORY_DESC)


class MovementIn(BaseModel):
    item: Optional[str] = Field(None, description="Kode item persis ATAU nama barang (cocok sebagian)")
    date_from: Optional[date] = Field(None, description="Tanggal transaksi mulai (YYYY-MM-DD)")
    date_to: Optional[date] = Field(None, description="Tanggal transaksi sampai (YYYY-MM-DD)")
    transaction_type: Optional[str] = Field(None, description="Tipe transaksi (cocok sebagian), mis. Receipt, Issue, Transfer")
    subinventory: Optional[str] = Field(None, description="Kode subinventory persis")
    group_by: Literal["type", "item", "day", "month"] = Field("type", description="Pengelompokan hasil")


class PoOutstandingIn(BaseModel):
    supplier: Optional[str] = Field(None, description="Nama supplier (cocok sebagian)")
    item: Optional[str] = Field(None, description="Kode item persis ATAU nama barang (cocok sebagian)")
    po_number: Optional[str] = Field(None, description="Nomor PO persis")
    late_only: bool = Field(False, description="true = hanya shipment yang sudah lewat tanggal janji kirim")
    group_by: Literal["none", "supplier"] = Field("none", description="none = detail per shipment; supplier = total per supplier")


class PoMatchIn(BaseModel):
    po_number: Optional[str] = Field(None, description="Nomor PO persis — untuk 'PO ini sudah ditagih belum?'")
    supplier: Optional[str] = Field(None, description="Nama supplier (cocok sebagian)")
    item: Optional[str] = Field(None, description="Kode item persis ATAU nama barang (cocok sebagian)")
    status: Optional[str] = Field(None, description=(
        "Filter match_status (awalan): 'Belum diterima', 'Diterima, belum ditagih penuh' (= uninvoiced receipts), "
        "'Ditagih melebihi penerimaan', 'Ditagih (2-way', 'Sebagian', 'Lengkap', 'Dibatalkan'"))
    group_by: Literal["none", "supplier", "status"] = Field("none", description="none = detail per distribusi; supplier / status = ringkasan")


class PrPendingIn(BaseModel):
    person: Optional[str] = Field(None, description="Nama/username pembuat (preparer) atau requester PR (cocok sebagian)")
    item: Optional[str] = Field(None, description="Kode item persis ATAU nama barang (cocok sebagian)")
    pr_number: Optional[str] = Field(None, description="Nomor PR persis")
    min_days_waiting: Optional[int] = Field(None, description="Hanya PR yang sudah menunggu minimal N hari sejak approve")
    group_by: Literal["none", "preparer"] = Field("none", description="none = detail per baris PR; preparer = ringkasan per pembuat")


class InvValueIn(BaseModel):
    item: Optional[str] = Field(None, description="Kode item persis ATAU nama barang (cocok sebagian)")
    item_category: Optional[list[str]] = Field(None, description=_CATEGORY_DESC)
    subinventory_type: Optional[Literal["GOOD", "REJECT", "QUARANTINE"]] = Field(None, description="Filter klasifikasi subinventory")
    group_by: Literal["category", "item", "subinventory_type"] = Field("category", description="Pengelompokan hasil")


class ArAgingIn(BaseModel):
    customer: Optional[str] = Field(None, description="Nama customer (cocok sebagian)")
    min_days_overdue: Optional[int] = Field(None, description="Hanya piutang yang lewat jatuh tempo minimal N hari")
    currency: Optional[str] = Field(None, description="Kode mata uang invoice, mis. USD")
    group_by: Literal["customer", "bucket", "customer_bucket"] = Field(
        "customer", description="customer = satu baris per customer dengan kolom per bucket; bucket = total per bucket; customer_bucket = customer × bucket")


class ArOpenIn(BaseModel):
    customer: Optional[str] = Field(None, description="Nama customer (cocok sebagian)")
    invoice_num: Optional[str] = Field(None, description="Nomor invoice/transaksi AR persis")
    min_days_overdue: Optional[int] = Field(None, description="Minimal hari lewat jatuh tempo")
    due_from: Optional[date] = Field(None, description="Jatuh tempo mulai (YYYY-MM-DD)")
    due_to: Optional[date] = Field(None, description="Jatuh tempo sampai (YYYY-MM-DD)")
    currency: Optional[str] = Field(None, description="Kode mata uang")


class ArReceiptIn(BaseModel):
    customer: Optional[str] = Field(None, description="Nama customer (cocok sebagian)")
    receipt_number: Optional[str] = Field(None, description="Nomor penerimaan persis")
    date_from: Optional[date] = Field(None, description="Tanggal penerimaan mulai (YYYY-MM-DD)")
    date_to: Optional[date] = Field(None, description="Tanggal penerimaan sampai (YYYY-MM-DD)")
    application_status: Optional[Literal["APP", "UNAPP", "ACC", "UNID"]] = Field(
        None, description="APP = sudah diaplikasikan ke invoice; UNAPP = belum diaplikasikan; ACC = on account; UNID = tidak teridentifikasi")
    include_reversed: bool = Field(False, description="true untuk ikut menampilkan penerimaan yang di-reverse")
    group_by: Literal["none", "customer", "month"] = Field("none", description="none = detail; customer / month = ringkasan")


class SoBacklogIn(BaseModel):
    customer: Optional[str] = Field(None, description="Nama customer (cocok sebagian)")
    item: Optional[str] = Field(None, description="Kode item persis ATAU nama produk (cocok sebagian)")
    order_number: Optional[str] = Field(None, description="Nomor sales order persis")
    business_type: Optional[Literal["Local", "Export", "CMO"]] = Field(None, description="Tipe bisnis")
    late_only: bool = Field(False, description="true = hanya baris yang lewat jadwal kirim dan masih ada sisa kirim")
    ordered_from: Optional[date] = Field(None, description="Tanggal order mulai (YYYY-MM-DD) — pakai untuk memisahkan backlog aktif dari order lama")
    ordered_to: Optional[date] = Field(None, description="Tanggal order sampai (YYYY-MM-DD)")
    group_by: Literal["none", "customer", "item", "year"] = Field(
        "none", description="none = detail per baris SO; customer / item = ringkasan; year = per tahun order (melihat backlog lama)")


class SoShipIn(BaseModel):
    order_number: Optional[str] = Field(None, description="Nomor sales order persis")
    customer: Optional[str] = Field(None, description="Nama customer (cocok sebagian)")
    item: Optional[str] = Field(None, description="Kode item persis ATAU nama produk (cocok sebagian)")
    status: Optional[str] = Field(None, description=(
        "Filter status kirim (awalan): Terkirim, Staged, Dirilis ke gudang, Belum dirilis, Backorder"))


class SalesIn(BaseModel):
    customer: Optional[str] = Field(None, description="Nama customer (cocok sebagian)")
    item: Optional[str] = Field(None, description="Kode item persis ATAU nama produk (cocok sebagian)")
    item_category: Optional[list[str]] = Field(None, description=_CATEGORY_DESC)
    period: Optional[str] = Field(None, description="Periode GL invoice: YYYY (setahun) atau YYYY-MM (sebulan). Kosong = semua periode.")
    business_type: Optional[Literal["Local", "Export", "CMO", "Non-SO"]] = Field(None, description="Tipe bisnis")
    group_by: Literal["customer", "item", "month", "customer_item", "business_type"] = Field(
        "customer", description="Pengelompokan hasil")


class BatchStatusIn(BaseModel):
    batch_no: Optional[str] = Field(None, description="Nomor batch persis")
    product: Optional[str] = Field(None, description="Kode produk persis ATAU nama produk (cocok sebagian)")
    status: Optional[Literal["Pending", "WIP", "Completed", "Closed", "Cancelled"]] = Field(None, description="Status batch")
    date_from: Optional[date] = Field(None, description="Rencana mulai batch dari (YYYY-MM-DD)")
    date_to: Optional[date] = Field(None, description="Rencana mulai batch sampai (YYYY-MM-DD)")
    late_only: bool = Field(False, description="true = hanya batch yang selesai terlambat atau belum selesai lewat rencana")
    group_by: Literal["none", "status", "schedule", "product", "month"] = Field(
        "none", description="none = detail per batch; status = jumlah per status; schedule = ketepatan jadwal (on-time %); product / month = ringkasan")


class BatchYieldIn(BaseModel):
    product: Optional[str] = Field(None, description="Kode produk persis ATAU nama produk (cocok sebagian)")
    batch_no: Optional[str] = Field(None, description="Nomor batch persis")
    date_from: Optional[date] = Field(None, description="Rencana mulai batch dari (YYYY-MM-DD)")
    date_to: Optional[date] = Field(None, description="Rencana mulai batch sampai (YYYY-MM-DD)")
    below_pct: Optional[float] = Field(None, description="Hanya yield di bawah persen ini, mis. 95")
    group_by: Literal["product", "batch", "month"] = Field("product", description="product = per produk; batch = per batch; month = per bulan")


class BatchMaterialIn(BaseModel):
    batch_no: Optional[str] = Field(None, description="Nomor batch persis")
    ingredient: Optional[str] = Field(None, description="Kode bahan persis ATAU nama bahan (cocok sebagian)")
    lot_number: Optional[str] = Field(None, description="Nomor lot bahan persis — untuk 'lot ini dipakai di batch mana'")
    over_pct: Optional[float] = Field(None, description="Hanya bahan dengan selisih aktual vs standar minimal N persen (absolut)")
    group_by: Literal["none", "ingredient"] = Field("none", description="none = detail per batch × bahan × lot; ingredient = ringkasan per bahan")


class PlIn(BaseModel):
    period: str = Field(..., description="YYYY = setahun penuh (termasuk periode penyesuaian); YYYY-MM atau JUL-26 = sebulan")
    ytd: bool = Field(False, description="true = Januari s.d. bulan pada `period` (YTD), tanpa periode penyesuaian")
    department: Optional[str] = Field(None, description="Kode atau nama departemen (segment3), cocok sebagian")
    compare_prior_year: bool = Field(False, description="true = tambah kolom periode yang sama tahun sebelumnya")
    level: Literal["line", "section"] = Field("line", description="line = per pos laba rugi; section = per bagian (Sales, COGS, OPEX, ...)")


class TbIn(BaseModel):
    period: str = Field(..., description="Satu periode bulan: YYYY-MM atau JUL-26")
    account: Optional[str] = Field(None, description="Awalan nomor akun (mis. 6113) ATAU nama akun (cocok sebagian, mis. listrik)")
    department: Optional[str] = Field(None, description="Kode atau nama departemen (cocok sebagian)")
    statement: Optional[Literal["BS", "PL"]] = Field(None, description="BS = akun neraca, PL = akun laba rugi")
    group_by: Literal["account", "fs_line", "department"] = Field(
        "account", description="account = per akun; fs_line = per pos neraca/laba rugi; department = per departemen")


class JournalIn(BaseModel):
    period: Optional[str] = Field(None, description="YYYY-MM atau JUL-26 (hanya 13 bulan terakhir tersedia)")
    date_from: Optional[date] = Field(None, description="Tanggal efektif mulai (YYYY-MM-DD)")
    date_to: Optional[date] = Field(None, description="Tanggal efektif sampai (YYYY-MM-DD)")
    account: Optional[str] = Field(None, description="Awalan nomor akun ATAU nama akun (cocok sebagian)")
    department: Optional[str] = Field(None, description="Kode atau nama departemen")
    source: Optional[str] = Field(None, description="Journal source (awalan), mis. Payables, Receivables, Manual, Inventory")
    category: Optional[str] = Field(None, description="Journal category (awalan), mis. Purchase Invoices, Adjustment")
    text: Optional[str] = Field(None, description="Cari di keterangan baris / nama jurnal (cocok sebagian)")
    subledger_txn: Optional[str] = Field(None, description="Nomor transaksi subledger persis (mis. nomor invoice AP/AR) — jurnal dari transaksi ini")
    min_amount: Optional[float] = Field(None, description="Hanya baris dengan nilai absolut minimal N Rupiah")
    group_by: Literal["none", "source", "account"] = Field("none", description="none = detail baris; source / account = ringkasan")


# ── Operations ───────────────────────────────────────────────────────────────

@app.post("/find_marts", operation_id="find_marts",
          summary="Cari mart & kolom yang relevan untuk pertanyaan bisnis (panggil ini dulu sebelum run_sql)")
async def find_marts(body: FindIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.find_marts, caller, body.keywords)


@app.post("/run_sql", operation_id="run_sql",
          summary="Jalankan satu SELECT read-only atas schema mart (untuk pertanyaan ad-hoc yang tidak dicakup intent tool)")
async def run_sql(body: SqlIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.run_sql, caller, body.sql, body.question)


class FreshIn(BaseModel):
    domain: Optional[str] = Field(None, description="Satu domain saja: AP, AR, PO, OM, INV, OPM, GL, CE, FA, MASTER. "
                                                    "Kosong = semua mart yang bisa Anda akses")


@app.post("/get_data_freshness", operation_id="get_data_freshness",
          summary="Daftar mart yang bisa Anda akses, jumlah baris, dan waktu data terakhir (as_of), opsional per domain")
async def get_data_freshness(body: Optional[FreshIn] = None, caller: Caller = Depends(current_caller)):
    return await _call(tools.get_data_freshness, caller, body.domain if body else None)


@app.post("/ap_get_aging", operation_id="ap_get_aging",
          summary="Aging hutang usaha (AP) per supplier dan bucket umur: Current, 1-30, 31-60, 61-90, >90 hari")
async def ap_get_aging(body: AgingIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.ap_get_aging, caller, **body.model_dump())


@app.post("/ap_get_open_invoices", operation_id="ap_get_open_invoices",
          summary="Daftar invoice supplier yang belum lunas, dengan jatuh tempo dan sisa hutang (valas + IDR)")
async def ap_get_open_invoices(body: OpenInvoiceIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.ap_get_open_invoices, caller, **body.model_dump())


@app.post("/ap_get_payments", operation_id="ap_get_payments",
          summary="Riwayat pembayaran ke supplier (per pembayaran, per supplier, atau per bulan)")
async def ap_get_payments(body: PaymentsIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.ap_get_payments, caller, **body.model_dump())


@app.post("/ap_get_holds", operation_id="ap_get_holds",
          summary="Invoice supplier yang sedang di-hold (belum di-release) beserta alasannya")
async def ap_get_holds(body: HoldsIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.ap_get_holds, caller, **body.model_dump())


@app.post("/inv_get_expiring_lots", operation_id="inv_get_expiring_lots",
          summary="Lot persediaan yang akan (atau sudah) kedaluwarsa dalam N hari, dengan qty dan satuan")
async def inv_get_expiring_lots(body: ExpiringIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.inv_get_expiring_lots, caller, **body.model_dump())


@app.post("/inv_get_onhand", operation_id="inv_get_onhand",
          summary="Stok on-hand saat ini per item, per subinventory, atau per lot (org 121)")
async def inv_get_onhand(body: OnhandIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.inv_get_onhand, caller, **body.model_dump())


@app.post("/inv_get_movements", operation_id="inv_get_movements",
          summary="Mutasi stok (masuk/keluar) per tipe transaksi, item, hari, atau bulan")
async def inv_get_movements(body: MovementIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.inv_get_movements, caller, **body.model_dump())


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


@app.post("/po_get_outstanding", operation_id="po_get_outstanding",
          summary="PO yang belum diterima penuh (sisa qty & nilai), tanggal janji kirim, dan keterlambatan")
async def po_get_outstanding(body: PoOutstandingIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.po_get_outstanding, caller, **body.model_dump())


@app.post("/po_get_match_status", operation_id="po_get_match_status",
          summary="Status PO: sudah diterima? sudah ditagih? invoice apa? (3-way match, uninvoiced receipts)")
async def po_get_match_status(body: PoMatchIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.po_get_match_status, caller, **body.model_dump())


@app.post("/pr_get_pending", operation_id="pr_get_pending",
          summary="Purchase requisition (PR) yang sudah approved tetapi belum dibuatkan PO")
async def pr_get_pending(body: PrPendingIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.pr_get_pending, caller, **body.model_dump())


@app.post("/inv_get_valuation", operation_id="inv_get_valuation",
          summary="Nilai persediaan org 121 (Rupiah) dengan biaya OPM PMAC, per kategori / item / klasifikasi subinventory")
async def inv_get_valuation(body: InvValueIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.inv_get_valuation, caller, **body.model_dump())


@app.post("/ar_get_aging", operation_id="ar_get_aging",
          summary="Aging piutang usaha (AR) per customer dan bucket — sama dengan laporan AR Outstanding dashboard")
async def ar_get_aging(body: ArAgingIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.ar_get_aging, caller, **body.model_dump())


@app.post("/ar_get_open_invoices", operation_id="ar_get_open_invoices",
          summary="Daftar invoice customer yang belum lunas, jatuh tempo dan sisa piutang (valas + IDR)")
async def ar_get_open_invoices(body: ArOpenIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.ar_get_open_invoices, caller, **body.model_dump())


@app.post("/ar_get_receipts", operation_id="ar_get_receipts",
          summary="Penerimaan kas dari customer dan aplikasinya ke invoice (termasuk unapplied / on account)")
async def ar_get_receipts(body: ArReceiptIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.ar_get_receipts, caller, **body.model_dump())


@app.post("/so_get_backlog", operation_id="so_get_backlog",
          summary="Sales order yang masih open: sisa qty & nilai belum dikirim, jadwal kirim, keterlambatan")
async def so_get_backlog(body: SoBacklogIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.so_get_backlog, caller, **body.model_dump())


@app.post("/so_get_shipment_status", operation_id="so_get_shipment_status",
          summary="Status pengiriman per baris SO: terkirim, staged, backorder, nomor delivery, tanggal ship confirm")
async def so_get_shipment_status(body: SoShipIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.so_get_shipment_status, caller, **body.model_dump())


@app.post("/sales_get_summary", operation_id="sales_get_summary",
          summary="Penjualan terinvoice per customer / item / bulan / tipe bisnis (nilai IDR, qty, credit memo)")
async def sales_get_summary(body: SalesIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.sales_get_summary, caller, **body.model_dump())


@app.post("/opm_get_batch", operation_id="opm_get_batch",
          summary="Status batch produksi OPM: status, formula, rencana vs aktual mulai/selesai, keterlambatan, ketepatan jadwal")
async def opm_get_batch(body: BatchStatusIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.opm_get_batch, caller, **body.model_dump())


@app.post("/opm_get_yield", operation_id="opm_get_yield",
          summary="Yield batch (aktual ÷ rencana produk) per produk, per batch, atau per bulan — batch Completed/Closed")
async def opm_get_yield(body: BatchYieldIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.opm_get_yield, caller, **body.model_dump())


@app.post("/opm_get_material_usage", operation_id="opm_get_material_usage",
          summary="Pemakaian bahan per batch (standar vs aktual) dan lot bahan yang dipakai — juga penelusuran lot → batch")
async def opm_get_material_usage(body: BatchMaterialIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.opm_get_material_usage, caller, **body.model_dump())


@app.post("/gl_get_pl", operation_id="gl_get_pl",
          summary="Laba rugi (P&L) per periode / YTD dengan subtotal — mapping sama dengan laporan Financial Statement dashboard")
async def gl_get_pl(body: PlIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.gl_get_pl, caller, **body.model_dump())


@app.post("/gl_get_trial_balance", operation_id="gl_get_trial_balance",
          summary="Trial balance satu periode: saldo awal, mutasi, saldo akhir per akun / pos / departemen")
async def gl_get_trial_balance(body: TbIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.gl_get_trial_balance, caller, **body.model_dump())


@app.post("/gl_get_journals", operation_id="gl_get_journals",
          summary="Detail jurnal GL posted (13 bulan terakhir) dan transaksi subledger asalnya (invoice/receipt)")
async def gl_get_journals(body: JournalIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.gl_get_journals, caller, **body.model_dump())


# ── Finance close, Cash Management, Fixed Assets ─────────────────────────────

_PERIOD_DESC = "Periode GL, format AUG-26 atau 2026-08"


class PeriodStatusIn(BaseModel):
    period: Optional[str] = Field(None, description=_PERIOD_DESC + ". Kosong = bulan berjalan dan dua bulan sebelumnya")
    application: Optional[Literal["GL", "AP", "AR", "PO", "INV", "OPM", "FA"]] = Field(
        None, description="Satu aplikasi saja; kosong = semua (INV = org 121, OPM = periode costing CKDO_PMAC)")


class SubledgerGapIn(BaseModel):
    period: Optional[str] = Field(None, description=_PERIOD_DESC + ". Kosong = semua periode (13 bulan terakhir)")
    application: Optional[str] = Field(None, description="AP, AR, PO, Cost Mgmt, OPM, FA, CE, GL (cocok sebagian)")
    group_by: Literal["summary", "detail"] = Field(
        "summary", description="summary = jumlah, nilai, dokumen tertua per jenis × aplikasi × periode; detail = daftar dokumen")


class UninvoicedIn(BaseModel):
    as_of_period: Optional[str] = Field(None, description=_PERIOD_DESC + " — hanya PO bertanggal sampai akhir periode ini")
    supplier: Optional[str] = Field(None, description="Nama supplier (cocok sebagian)")
    group_by: Literal["supplier", "po"] = Field("supplier", description="supplier = total per supplier; po = detail per baris PO")


class ShippedNotInvoicedIn(BaseModel):
    date_from: Optional[date] = Field(None, description="Tanggal kirim mulai (YYYY-MM-DD)")
    customer: Optional[str] = Field(None, description="Nama customer (cocok sebagian)")


class UnappliedIn(BaseModel):
    customer: Optional[str] = Field(None, description="Nama customer (cocok sebagian)")


class AutoInvoiceIn(BaseModel):
    date_from: Optional[date] = Field(None, description="Baris interface dibuat mulai tanggal (YYYY-MM-DD)")
    so_number: Optional[str] = Field(None, description="Nomor SO persis")
    group_by: Literal["none", "error"] = Field("none", description="none = per baris; error = jumlah per pesan error")


class OpenBatchIn(BaseModel):
    status: Optional[Literal["Pending", "WIP", "Completed"]] = Field(None, description="Satu status saja; kosong = semua yang belum Closed")
    days_open: Optional[int] = Field(None, ge=0, description="Hanya batch yang terbuka minimal N hari sejak mulai (aktual, atau rencana)")


class UnreconciledIn(BaseModel):
    bank_account_name: Optional[str] = Field(None, description="Nama rekening atau nama bank (cocok sebagian), mis. BCA")
    date_to: Optional[date] = Field(None, description="Transaksi sampai tanggal (YYYY-MM-DD)")
    side: Optional[Literal["BANK", "SYSTEM"]] = Field(
        None, description="BANK = di rekening koran belum ada di sistem; SYSTEM = di sistem belum muncul di rekening koran")
    group_by: Literal["summary", "detail"] = Field("summary", description="summary = per rekening × sisi × sumber; detail = per transaksi")


class AssetsIn(BaseModel):
    category: Optional[str] = Field(None, description="Kategori aset (kode atau deskripsi, cocok sebagian)")
    location: Optional[str] = Field(None, description="Lokasi aset (cocok sebagian)")
    asset: Optional[str] = Field(None, description="Nomor aset / tag persis, atau deskripsi (cocok sebagian)")
    status: Optional[Literal["Aktif", "CIP", "Retired", "Fully reserved"]] = Field(None, description="Status aset")
    group_by: Literal["category", "location", "status", "asset"] = Field(
        "category", description="Ringkas per kategori / lokasi / status, atau asset = daftar per aset")


class DeprnIn(BaseModel):
    period: str = Field(..., description="Periode FA, format AUG-26 atau 2026-08")
    category: Optional[str] = Field(None, description="Kategori aset (cocok sebagian)")
    group_by: Literal["category", "asset"] = Field("category", description="category = total per kategori; asset = per aset")


@app.post("/gl_get_period_status", operation_id="gl_get_period_status",
          summary="Status periode per aplikasi (GL, AP, AR, PO, INV, OPM costing, FA) — Open/Closed, penyusutan sudah dijalankan")
async def gl_get_period_status(body: PeriodStatusIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.gl_get_period_status, caller, **body.model_dump())


@app.post("/gl_get_subledger_gap", operation_id="gl_get_subledger_gap",
          summary="Selisih subledger vs GL: event belum di-account/error, entry draft, final belum transfer, jurnal GL belum posting")
async def gl_get_subledger_gap(body: SubledgerGapIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.gl_get_subledger_gap, caller, **body.model_dump())


@app.post("/po_get_uninvoiced_receipts", operation_id="po_get_uninvoiced_receipts",
          summary="Barang sudah diterima tetapi belum ditagih supplier (dasar accrual), per supplier atau per PO, nilai IDR")
async def po_get_uninvoiced_receipts(body: UninvoicedIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.po_get_uninvoiced_receipts, caller, **body.model_dump())


@app.post("/so_get_shipped_not_invoiced", operation_id="so_get_shipped_not_invoiced",
          summary="Baris SO yang sudah dikirim tetapi belum menjadi invoice AR, dengan error AutoInvoice jika ada")
async def so_get_shipped_not_invoiced(body: ShippedNotInvoicedIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.so_get_shipped_not_invoiced, caller, **body.model_dump())


@app.post("/ar_get_unapplied_receipts", operation_id="ar_get_unapplied_receipts",
          summary="Penerimaan customer yang belum di-apply ke invoice (unapplied / on account)")
async def ar_get_unapplied_receipts(body: UnappliedIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.ar_get_unapplied_receipts, caller, **body.model_dump())


@app.post("/ar_get_autoinvoice_errors", operation_id="ar_get_autoinvoice_errors",
          summary="Baris interface AutoInvoice yang ditolak atau masih menunggu, dengan pesan error dan nomor SO")
async def ar_get_autoinvoice_errors(body: AutoInvoiceIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.ar_get_autoinvoice_errors, caller, **body.model_dump())


@app.post("/opm_get_open_batches", operation_id="opm_get_open_batches",
          summary="Batch OPM yang belum Closed (Pending/WIP/Completed) dan sudah berapa hari terbuka")
async def opm_get_open_batches(body: OpenBatchIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.opm_get_open_batches, caller, **body.model_dump())


@app.post("/ce_get_unreconciled", operation_id="ce_get_unreconciled",
          summary="Rekonsiliasi bank: item rekening koran dan transaksi sistem yang belum rekon, dengan tanggal statement terakhir")
async def ce_get_unreconciled(body: UnreconciledIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.ce_get_unreconciled, caller, **body.model_dump())


@app.post("/fa_get_assets", operation_id="fa_get_assets",
          summary="Aset tetap: harga perolehan, akumulasi penyusutan, nilai buku (NBV) per kategori / lokasi / status / aset")
async def fa_get_assets(body: AssetsIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.fa_get_assets, caller, **body.model_dump())


@app.post("/fa_get_depreciation", operation_id="fa_get_depreciation",
          summary="Penyusutan aset tetap satu periode per kategori atau per aset (beban periode, YTD, akumulasi)")
async def fa_get_depreciation(body: DeprnIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.fa_get_depreciation, caller, **body.model_dump())


# ── Rest of the library v2 catalog ───────────────────────────────────────────

class LookupIn(BaseModel):
    text: str = Field(..., description="Nama sebagian atau kode, mis. 'mannitol', 'kyongbo', 'listrik', '511111'")
    type: Optional[Literal["item", "supplier", "customer", "account", "department"]] = Field(
        None, description="Jenis master; kosong = semua jenis")


class PoDocIn(BaseModel):
    po_number: str = Field(..., description="Nomor PO persis")


class PendingApprovalIn(BaseModel):
    min_days: Optional[int] = Field(None, ge=0, description="Hanya yang menunggu minimal N hari")
    doc_type: Optional[Literal["PO", "PR"]] = Field(None, description="PO atau PR (requisition); kosong = keduanya")
    approver: Optional[str] = Field(None, description="Nama approver yang ditunggu (cocok sebagian)")
    include_incomplete: bool = Field(False, description="true = ikut draft yang belum pernah di-submit (status Incomplete)")


class ApInvoiceIn(BaseModel):
    invoice_num: str = Field(..., description="Nomor invoice supplier persis")
    supplier: Optional[str] = Field(None, description="Nama supplier (cocok sebagian) jika nomor invoice dipakai beberapa supplier")


class DueForecastIn(BaseModel):
    weeks_ahead: int = Field(8, ge=1, le=52, description="Berapa minggu ke depan (default 8)")
    supplier: Optional[str] = Field(None, description="Nama supplier (cocok sebagian)")


class WithholdingIn(BaseModel):
    period: Optional[str] = Field(None, description="Periode GL, format AUG-26 atau 2026-08 (24 bulan terakhir)")
    tax_code: Optional[str] = Field(None, description="Nama kode pajak withholding (cocok sebagian), mis. PPh 23")
    supplier: Optional[str] = Field(None, description="Nama supplier (cocok sebagian)")
    group_by: Literal["tax", "supplier", "invoice"] = Field("tax", description="tax = per kode pajak; supplier = per supplier; invoice = detail")


class SoOrderIn(BaseModel):
    order_number: str = Field(..., description="Nomor sales order persis")


class SoHoldIn(BaseModel):
    hold_name: Optional[str] = Field(None, description="Nama hold (cocok sebagian), mis. Credit Check")
    customer: Optional[str] = Field(None, description="Nama customer (cocok sebagian)")


class CustomerBalanceIn(BaseModel):
    customer: str = Field(..., description="Nama customer (cocok sebagian)")


class StockCardIn(BaseModel):
    item: str = Field(..., description="Kode item persis (pakai lookup_master jika hanya tahu nama)")
    period: str = Field(..., description="Bulan, format AUG-26 atau 2026-08")
    subinventory: Optional[str] = Field(None, description="Kode subinventory persis; kosong = semua")


class SlowMovingIn(BaseModel):
    days_no_movement: int = Field(180, ge=1, le=3650, description="Tidak ada mutasi minimal N hari (default 180)")
    subinventory_type: Optional[Literal["GOOD", "REJECT", "QUARANTINE"]] = Field("GOOD", description="Default GOOD; null = semua")


class ItemCostIn(BaseModel):
    item: str = Field(..., description="Kode item persis atau nama (cocok sebagian)")
    period: Optional[str] = Field(None, description="Bulan, format AUG-26 atau 2026-08; kosong = 13 periode terakhir")


class AccountMovementIn(BaseModel):
    account: str = Field(..., description="Kode akun (awalan, mis. 5111) atau nama akun (cocok sebagian, mis. 'listrik')")
    period_from: str = Field(..., description="Periode awal, format AUG-26 atau 2026-08")
    period_to: Optional[str] = Field(None, description="Periode akhir; kosong = sama dengan period_from")
    department: Optional[str] = Field(None, description="Kode departemen (segment3) atau nama (cocok sebagian)")


class BudgetIn(BaseModel):
    period: str = Field(..., description="YYYY (setahun), YYYY-MM atau AUG-26 (sebulan)")
    ytd: bool = Field(False, description="true = Januari s.d. bulan period")
    department: Optional[str] = Field(None, description="Kode departemen (segment3) atau nama (cocok sebagian)")
    account: Optional[str] = Field(None, description="Kode akun (awalan) atau nama akun (cocok sebagian)")
    budget_name: Optional[str] = Field(None, description="Nama versi budget; kosong = versi dengan data terbanyak di periode itu")
    include_revenue: bool = Field(False, description="true = ikut akun pendapatan; default hanya biaya")
    group_by: Literal["department", "account", "section", "month"] = Field("department", description="Dimensi ringkasan")


@app.post("/lookup_master", operation_id="lookup_master",
          summary="Cari kode dari nama sebagian (atau nama dari kode): item, supplier, customer, akun, departemen")
async def lookup_master(body: LookupIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.lookup_master, caller, **body.model_dump())


@app.post("/po_get_document", operation_id="po_get_document",
          summary="Detail satu PO (open atau closed): semua baris/shipment, qty pesan/terima/tagih/batal/outstanding, payment term, PR & requestor, receipt terakhir, kategori/material type/negara asal, invoice terkait")
async def po_get_document(body: PoDocIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.po_get_document, caller, **body.model_dump())


@app.post("/po_get_pending_approval", operation_id="po_get_pending_approval",
          summary="PO dan PR yang masih menunggu approval: approver yang ditunggu dan sudah berapa hari")
async def po_get_pending_approval(body: PendingApprovalIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.po_get_pending_approval, caller, **body.model_dump())


@app.post("/ap_get_invoice", operation_id="ap_get_invoice",
          summary="Detail satu invoice supplier (lunas atau belum): nilai, status bayar, jatuh tempo, pembayaran, hold")
async def ap_get_invoice(body: ApInvoiceIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.ap_get_invoice, caller, **body.model_dump())


@app.post("/ap_get_due_forecast", operation_id="ap_get_due_forecast",
          summary="Proyeksi kebutuhan kas pembayaran supplier per minggu ke depan (plus yang sudah lewat jatuh tempo)")
async def ap_get_due_forecast(body: DueForecastIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.ap_get_due_forecast, caller, **body.model_dump())


@app.post("/ap_get_withholding", operation_id="ap_get_withholding",
          summary="Pajak dipotong (withholding/PPh) dari invoice supplier per kode pajak, supplier, atau invoice")
async def ap_get_withholding(body: WithholdingIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.ap_get_withholding, caller, **body.model_dump())


@app.post("/so_get_order", operation_id="so_get_order",
          summary="Detail satu sales order (open atau closed): baris, qty pesan/kirim/invoice, delivery, lot, nomor invoice")
async def so_get_order(body: SoOrderIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.so_get_order, caller, **body.model_dump())


@app.post("/so_get_holds", operation_id="so_get_holds",
          summary="Sales order yang sedang di-hold (credit hold, hold manual) dan sudah berapa lama")
async def so_get_holds(body: SoHoldIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.so_get_holds, caller, **body.model_dump())


@app.post("/ar_get_customer_balance", operation_id="ar_get_customer_balance",
          summary="Saldo piutang satu customer per mata uang: total, overdue, jatuh tempo tertua, dan receipt unapplied")
async def ar_get_customer_balance(body: CustomerBalanceIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.ar_get_customer_balance, caller, **body.model_dump())


@app.post("/inv_get_stock_card", operation_id="inv_get_stock_card",
          summary="Kartu stok satu item satu bulan: saldo awal, masuk/keluar per hari × tipe transaksi, saldo berjalan, saldo akhir")
async def inv_get_stock_card(body: StockCardIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.inv_get_stock_card, caller, **body.model_dump())


@app.post("/inv_get_slow_moving", operation_id="inv_get_slow_moving",
          summary="Item slow moving: masih ada stok tetapi tidak bergerak N hari, dengan qty dan tanggal gerak terakhir")
async def inv_get_slow_moving(body: SlowMovingIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.inv_get_slow_moving, caller, **body.model_dump())


@app.post("/opm_get_item_cost", operation_id="opm_get_item_cost",
          summary="Biaya aktual OPM (PMAC) satu item per periode costing, perbandingan periode sebelumnya, dan komponen biaya")
async def opm_get_item_cost(body: ItemCostIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.opm_get_item_cost, caller, **body.model_dump())


@app.post("/gl_get_account_movement", operation_id="gl_get_account_movement",
          summary="Mutasi akun per bulan dalam rentang periode: saldo awal, debit, kredit, saldo akhir")
async def gl_get_account_movement(body: AccountMovementIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.gl_get_account_movement, caller, **body.model_dump())


@app.post("/gl_get_budget_vs_actual", operation_id="gl_get_budget_vs_actual",
          summary="Budget vs encumbrance vs realisasi per departemen / akun / pos / bulan, sisa budget dan % realisasi")
async def gl_get_budget_vs_actual(body: BudgetIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.gl_get_budget_vs_actual, caller, **body.model_dump())


# ── PAC Business Plan ────────────────────────────────────────────────────────

class BusinessPlanIn(BaseModel):
    year: Optional[int] = Field(None, description="Tahun Business Plan, mis. 2026. Kosong = tahun plan terbaru.")
    section: Optional[str] = Field(None, description=(
        "Bagian dokumen: nomor (1-1 P&L tahunan, 1-2 P&L bulanan, 1-2.a Local, 1-2.b CMO, 1-2.c Export, "
        "2-1 sales plan nilai, 2-2 sales plan qty, 3-1 COGS per bisnis, 3-2 COGS per produk, 4 manufacture, "
        "5 investasi, 6-1 purchase nilai, 6-2 purchase qty, 7 registrasi, 8 marketing, 9 personel, 10 cashflow) "
        "atau nama (P&L, sales, COGS, manufacture, investment, purchase, personnel, cashflow). Kode bertanda "
        "-/. (1-2) = sheet itu saja; angka saja (1) = semua sub-bagiannya. "
        "Kosong bersama line = daftar bagian saja."))
    line: Optional[str] = Field(None, description="Label baris (cocok sebagian pada jalur induk > anak), mis. 'Net Sales', "
                                                  "'Gross Profit', 'Export', nama produk, nama departemen")
    period: Optional[str] = Field(None, description="tahunan = semua kolom tahunan (total plan + angka tahun pembanding), "
                                                    "YYYY = kolom tahunan tahun itu saja, YYYY-MM = satu bulan, "
                                                    "YYYY-Qn = satu kuartal. Kosong = semua kolom (termasuk bulanan).")
    scenario: Optional[Literal["plan", "pembanding"]] = Field(None, description="plan = rencana; pembanding = angka "
                                                                               "tahun sebelumnya di dokumen")
    measure: Optional[Literal["value", "ratio", "growth"]] = Field(None, description="value = angka; ratio/growth = persen")


class PlanVsActualIn(BaseModel):
    year: int = Field(..., description="Tahun, mis. 2026")
    month: Optional[int] = Field(None, description="Bulan 1–12; kosong = setahun penuh (Jan–Des)")
    ytd: bool = Field(False, description="true = Januari s.d. month")
    basis: Literal["gross", "net", "customer"] = Field("gross", description=(
        "Baris plan yang dibandingkan: gross = CKD OTTO Gross Sales (paling sebanding dengan invoice EBS, default); "
        "net = Net Sales (setelah distribution fee, diskon, retur, freight); customer = Customer Sales "
        "(penjualan distributor ke pasar)"))
    group_by: Literal["business", "month", "business_month"] = Field("business", description="Dimensi ringkasan")


@app.post("/pac_get_business_plan", operation_id="pac_get_business_plan",
          summary="Angka Business Plan PAC (rencana/target): P&L, sales plan per produk, COGS, manufacture, "
                  "investasi, purchase, personel, cashflow — per tahun, bulan, kuartal")
async def pac_get_business_plan(body: BusinessPlanIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.pac_get_business_plan, caller, **body.model_dump())


@app.post("/pac_get_sales_plan_vs_actual", operation_id="pac_get_sales_plan_vs_actual",
          summary="Target penjualan Business Plan vs realisasi invoice EBS per bisnis (Local/CMO/Export): "
                  "sebulan, YTD atau setahun, selisih dan % pencapaian")
async def pac_get_sales_plan_vs_actual(body: PlanVsActualIn, caller: Caller = Depends(current_caller)):
    return await _call(tools.pac_get_sales_plan_vs_actual, caller, **body.model_dump())


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}
