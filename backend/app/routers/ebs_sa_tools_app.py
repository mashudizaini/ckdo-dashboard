"""
CKDO EBS System Administration Tools — the sa_* tools (library v2 3.2b) as
their own OpenAPI tool server, mounted at /api/v1/ebs-sa-tools.

A second server rather than more operations on /api/v1/ebs-tools: Open WebUI
grants visibility per tool server, not per operation, so this is what lets
the sa_* tools be visible to the ebs-sysadmin group only (fence 1) while
every business user keeps seeing the EBS Data Tools.

Same identity rules as ebs_tools_app (Keycloak token, or service key plus
X-OpenWebUI-User-Email). On top of that every operation depends on
require_sysadmin: the caller's email must be in SYSADMIN_ALLOWLIST (fence 2);
the SQL then runs as llm_sa_ro (fence 3, see sa_tools.py).
"""
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.routers.ebs_tools_app import _call, _denied, _failed, _rejected, current_caller
from app.services.ebs_mart import query, sa_tools
from app.services.ebs_mart.access import AccessDenied, Caller
from app.services.ebs_mart.query import QueryFailed
from app.services.ebs_mart.sql_guard import SqlRejected

app = FastAPI(
    title="CKDO EBS System Administration Tools",
    description=(
        "Akses read-only ke data System Administration Oracle EBS PT CKD OTTO Pharmaceuticals: user, "
        "responsibility, akses fungsi, segregation of duties, profile option, riwayat login, concurrent "
        "request & manager, approval workflow tertahan, patch, Forms Personalization. Hanya untuk tim IT "
        "yang ada di allowlist. Setiap hasil membawa as_of, sql_used, row_count dan truncated."
    ),
    version="1.0.0",
    root_path_in_servers=False,
)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://cochat(-dev)?\.ckd-otto\.com",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.add_exception_handler(SqlRejected, _rejected)
app.add_exception_handler(AccessDenied, _denied)
app.add_exception_handler(QueryFailed, _failed)


async def require_sysadmin(caller: Caller = Depends(current_caller)) -> Caller:
    """Blueprint v2 section 7: the email allowlist decides, never a group.
    Refusals are logged like every other call."""
    if not caller.is_sysadmin:
        await _call(query.log_call, caller, tool="sysadmin", status="DENIED",
                    error="Bukan anggota allowlist System Administration")
        raise HTTPException(403, "Data System Administration hanya untuk tim IT tertentu.")
    return caller


# ── Request bodies ───────────────────────────────────────────────────────────

class UserIn(BaseModel):
    user: str = Field(..., description="User name EBS persis (mis. BUDI.SANTOSO) atau sebagian nama karyawan / email")


class UserRespIn(BaseModel):
    user: str = Field(..., description="User name EBS persis atau sebagian nama karyawan")
    include_inactive: bool = Field(False, description="true = ikut tampilkan responsibility yang sudah end-dated")


class WhoRespIn(BaseModel):
    responsibility: str = Field(..., description="Nama responsibility (cocok sebagian), mis. 'Payables Manager'")
    include_inactive: bool = Field(False, description="true = ikut tampilkan assignment yang sudah tidak aktif")


class WhoFunctionIn(BaseModel):
    function: str = Field(..., description="Nama fungsi yang tampil di menu (cocok sebagian), mis. 'Invoices' atau 'Payments', "
                                           "ATAU kode fungsi persis, mis. AP_APXINWKB")
    include_seeded: bool = Field(False, description="true = ikut user seeded (SYSADMIN, dll.)")


class RespFunctionsIn(BaseModel):
    responsibility: str = Field(..., description="Nama responsibility (cocok sebagian)")
    function: Optional[str] = Field(None, description="Saring nama/kode fungsi (cocok sebagian)")
    function_type: Optional[str] = Field(None, description="Tipe fungsi persis: FORM, JSP, SUBFUNCTION, WWW, ...")
    include_unheld: bool = Field(False, description="true = ikut responsibility yang saat ini tidak dipegang user aktif mana pun")


class RespProgramsIn(BaseModel):
    responsibility: Optional[str] = Field(None, description="Nama responsibility (cocok sebagian)")
    program: Optional[str] = Field(None, description="Nama atau kode program concurrent (cocok sebagian)")
    include_unheld: bool = Field(False, description="true = ikut responsibility yang saat ini tidak dipegang user aktif mana pun")


class DormantIn(BaseModel):
    days: int = Field(90, ge=1, le=3650, description="User aktif yang tidak login minimal N hari (default 90)")
    exclude_seeded: bool = Field(True, description="Kecualikan user seeded (SYSADMIN, GUEST, user sistem)")


class SodIn(BaseModel):
    rule_name: Optional[str] = Field(None, description="Nama aturan SoD (cocok sebagian), mis. 'pembayaran'")
    user: Optional[str] = Field(None, description="User name atau nama karyawan (cocok sebagian)")
    include_seeded: bool = Field(False, description="true = ikut user seeded")


class ProfileIn(BaseModel):
    profile: str = Field(..., description="Nama profile option (user profile name atau kode, cocok sebagian), "
                                          "mis. 'MO: Operating Unit' atau 'Sign-On:Audit Level'")
    level: Optional[Literal["Site", "Application", "Responsibility", "User", "Server", "Organization"]] = Field(
        None, description="Hanya level ini")
    value_owner: Optional[str] = Field(None, description="User name EBS: tampilkan hanya nilai yang berlaku untuk user ini, "
                                                          "urut prioritas (User > Responsibility > Application > Site)")


class LoginIn(BaseModel):
    user: str = Field(..., description="User name EBS persis atau sebagian nama karyawan")
    days: int = Field(7, ge=1, le=90, description="N hari terakhir (maks 90)")


class ManagerIn(BaseModel):
    only_problems: bool = Field(False, description="true = hanya manager yang kurang proses / down")


class ApprovalIn(BaseModel):
    approver: Optional[str] = Field(None, description="Penerima notifikasi: role/user name atau nama (cocok sebagian)")
    days: int = Field(3, ge=0, le=3650, description="Terbuka minimal N hari (default 3)")
    item_type: Optional[str] = Field(None, description="Tipe workflow: kode persis (POAPPRV = approval PO, REQAPPRV = "
                                                       "requisition, APINVAPR = invoice AP) atau nama (cocok sebagian)")
    include_fyi: bool = Field(False, description="true = ikut notifikasi FYI yang tidak butuh respons")
    include_errors: bool = Field(False, description="true = ikut notifikasi error workflow (WFERROR, POERROR, ...) — bukan approval")
    group_by: Literal["none", "recipient", "item_type"] = Field(
        "none", description="none = detail per notifikasi; recipient = jumlah per penerima; item_type = per jenis workflow")


class PatchIn(BaseModel):
    patch_number: str = Field(..., description="Nomor patch/bug, satu atau beberapa dipisah koma, mis. '33466457, 31856779'")


class FormPersIn(BaseModel):
    form: Optional[str] = Field(None, description="Nama form atau fungsi (cocok sebagian), mis. POXPOEPO")


class ConcRequestIn(BaseModel):
    hours: int = Field(24, ge=1, le=720, description="N jam terakhir menurut request_date (maks 720 = 30 hari)")
    status: Optional[str] = Field(None, description="error, warning, normal, terminated, cancelled, hold, 'no manager', "
                                                    "atau 'gagal' (= error + terminated)")
    phase: Optional[Literal["Pending", "Running", "Completed", "Inactive"]] = Field(None, description="Fase request")
    program: Optional[str] = Field(None, description="Nama atau kode program concurrent (cocok sebagian)")
    user: Optional[str] = Field(None, description="User yang men-submit (user name / nama, cocok sebagian)")
    group_by: Literal["none", "program", "status"] = Field(
        "none", description="none = detail per request; program = jumlah & durasi per program; status = jumlah per fase/status")


# ── Tools ────────────────────────────────────────────────────────────────────

@app.post("/sa_get_user", operation_id="sa_get_user",
          summary="Profil user EBS: status aktif, tanggal, last login, karyawan terkait & status karyawannya")
async def sa_get_user(body: UserIn, caller: Caller = Depends(require_sysadmin)):
    return await _call(sa_tools.sa_get_user, caller, **body.model_dump())


@app.post("/sa_get_user_resps", operation_id="sa_get_user_resps",
          summary="Responsibility milik user (direct dan indirect/role UMX) dengan tanggal mulai/akhir")
async def sa_get_user_resps(body: UserRespIn, caller: Caller = Depends(require_sysadmin)):
    return await _call(sa_tools.sa_get_user_resps, caller, **body.model_dump())


@app.post("/sa_who_has_resp", operation_id="sa_who_has_resp",
          summary="Daftar user aktif yang memegang sebuah responsibility")
async def sa_who_has_resp(body: WhoRespIn, caller: Caller = Depends(require_sysadmin)):
    return await _call(sa_tools.sa_who_has_resp, caller, **body.model_dump())


@app.post("/sa_who_has_function", operation_id="sa_who_has_function",
          summary="User aktif yang bisa mengakses sebuah fungsi/menu, lewat responsibility apa (direct/indirect)")
async def sa_who_has_function(body: WhoFunctionIn, caller: Caller = Depends(require_sysadmin)):
    return await _call(sa_tools.sa_who_has_function, caller, **body.model_dump())


@app.post("/sa_get_resp_functions", operation_id="sa_get_resp_functions",
          summary="Fungsi efektif sebuah responsibility (setelah exclusion fungsi & menu)")
async def sa_get_resp_functions(body: RespFunctionsIn, caller: Caller = Depends(require_sysadmin)):
    return await _call(sa_tools.sa_get_resp_functions, caller, **body.model_dump())


@app.post("/sa_get_resp_programs", operation_id="sa_get_resp_programs",
          summary="Program/request set yang boleh dijalankan sebuah responsibility, atau responsibility yang bisa menjalankan sebuah program")
async def sa_get_resp_programs(body: RespProgramsIn, caller: Caller = Depends(require_sysadmin)):
    return await _call(sa_tools.sa_get_resp_programs, caller, **body.model_dump())


@app.post("/sa_get_dormant_users", operation_id="sa_get_dormant_users",
          summary="User EBS aktif yang tidak login N hari (atau belum pernah login)")
async def sa_get_dormant_users(body: DormantIn, caller: Caller = Depends(require_sysadmin)):
    return await _call(sa_tools.sa_get_dormant_users, caller, **body.model_dump())


@app.post("/sa_get_terminated_active_users", operation_id="sa_get_terminated_active_users",
          summary="User EBS yang masih aktif padahal karyawannya sudah tidak aktif/keluar")
async def sa_get_terminated_active_users(caller: Caller = Depends(require_sysadmin)):
    return await _call(sa_tools.sa_get_terminated_active_users, caller)


@app.post("/sa_get_sod_violations", operation_id="sa_get_sod_violations",
          summary="Pelanggaran segregation of duties per user dan aturan, urut risiko tertinggi")
async def sa_get_sod_violations(body: SodIn, caller: Caller = Depends(require_sysadmin)):
    return await _call(sa_tools.sa_get_sod_violations, caller, **body.model_dump())


@app.post("/sa_get_profile_value", operation_id="sa_get_profile_value",
          summary="Nilai profile option per level (Site/Application/Responsibility/User) dan urutan prioritasnya")
async def sa_get_profile_value(body: ProfileIn, caller: Caller = Depends(require_sysadmin)):
    return await _call(sa_tools.sa_get_profile_value, caller, **body.model_dump())


@app.post("/sa_get_login_history", operation_id="sa_get_login_history",
          summary="Riwayat login user N hari terakhir (maks 90) dengan responsibility dan form yang dibuka")
async def sa_get_login_history(body: LoginIn, caller: Caller = Depends(require_sysadmin)):
    return await _call(sa_tools.sa_get_login_history, caller, **body.model_dump())


@app.post("/sa_get_manager_status", operation_id="sa_get_manager_status",
          summary="Status concurrent manager: proses target vs aktual, request yang sedang berjalan")
async def sa_get_manager_status(body: ManagerIn, caller: Caller = Depends(require_sysadmin)):
    return await _call(sa_tools.sa_get_manager_status, caller, **body.model_dump())


@app.post("/sa_get_pending_approvals", operation_id="sa_get_pending_approvals",
          summary="Notifikasi approval workflow yang masih terbuka (tertahan) dan lama menunggunya")
async def sa_get_pending_approvals(body: ApprovalIn, caller: Caller = Depends(require_sysadmin)):
    return await _call(sa_tools.sa_get_pending_approvals, caller, **body.model_dump())


@app.post("/sa_check_patch", operation_id="sa_check_patch",
          summary="Apakah patch (nomor bug) sudah diterapkan di EBS, dan kapan")
async def sa_check_patch(body: PatchIn, caller: Caller = Depends(require_sysadmin)):
    return await _call(sa_tools.sa_check_patch, caller, **body.model_dump())


@app.post("/sa_get_form_personalizations", operation_id="sa_get_form_personalizations",
          summary="Rule Forms Personalization yang aktif per form/fungsi")
async def sa_get_form_personalizations(body: FormPersIn, caller: Caller = Depends(require_sysadmin)):
    return await _call(sa_tools.sa_get_form_personalizations, caller, **body.model_dump())


@app.post("/it_get_concurrent_requests", operation_id="it_get_concurrent_requests",
          summary="Concurrent request N jam terakhir: program, user, status (error/warning), durasi, pesan penyelesaian")
async def it_get_concurrent_requests(body: ConcRequestIn, caller: Caller = Depends(require_sysadmin)):
    return await _call(sa_tools.it_get_concurrent_requests, caller, **body.model_dump())


class InterfaceIn(BaseModel):
    interface: Optional[Literal["AP", "AR", "GL", "INV", "RCV"]] = Field(
        None, description="AP = import invoice, AR = AutoInvoice, GL = journal import, INV = transaksi inventory "
                          "(interface + pending MMTT), RCV = receiving. Kosong = semua")
    status: Optional[Literal["ERROR", "PENDING"]] = Field(None, description="ERROR = ditolak; PENDING = belum diproses")
    days: Optional[int] = Field(None, ge=1, le=3650, description="Hanya baris yang dibuat N hari terakhir")
    group_by: Literal["summary", "detail"] = Field("summary", description="summary = per interface × status × pesan error; detail = per baris")


@app.post("/it_get_interface_errors", operation_id="it_get_interface_errors",
          summary="Error dan antrean open interface (AP, AR AutoInvoice, GL, inventory, receiving) dengan pesan error")
async def it_get_interface_errors(body: InterfaceIn, caller: Caller = Depends(require_sysadmin)):
    return await _call(sa_tools.it_get_interface_errors, caller, **body.model_dump())


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}
