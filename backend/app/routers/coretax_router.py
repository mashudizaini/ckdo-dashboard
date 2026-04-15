"""
coretax_router.py
FastAPI router untuk bulk download eBupot BPU dari Coretax DJP.

Dua mode operasi:
  Mode 1 — Cookie (DIANJURKAN):
    User login manual di browser Chrome, copy nilai header "Cookie:" dari DevTools,
    paste ke form. Playwright langsung buka halaman issued tanpa login otomatis.

  Mode 2 — Login otomatis (username + password + CAPTCHA):
    Playwright buka halaman login, pause tunggu CAPTCHA diisi manual lewat UI,
    lalu lanjut login, pilih NPWP perusahaan, navigasi ke halaman issued.

Alur download (sama untuk kedua mode):
  → Filter masa pajak → klik PDF tiap baris → zip semua → siap diunduh

Dependency: pip install playwright fastapi python-multipart
             playwright install chromium
"""

import asyncio
import zipfile
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

try:
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

coretax_router = APIRouter(prefix="/api/coretax", tags=["Coretax"])

LOGIN_URL  = "https://coretaxdjp.pajak.go.id/identityproviderportal/Account/Login"
ISSUED_URL = "https://coretaxdjp.pajak.go.id/withholding-slips-portal/id-ID/ebupotbpu/issued"

DOWNLOAD_DIR = Path("downloads/coretax")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ─── In-memory job store ──────────────────────────────────────────────────────
jobs: dict[str, dict] = {}


# ─── Schema ──────────────────────────────────────────────────────────────────
class StartJobRequest(BaseModel):
    # ── Mode 1: Cookie (DIANJURKAN) ──────────────────────────────────────────
    # Cara ambil: Login di Chrome → F12 → Network → klik request apapun ke
    # coretaxdjp.pajak.go.id → Headers → salin seluruh nilai "Cookie:"
    cookie_string: Optional[str] = None

    # ── Mode 2: Login otomatis ───────────────────────────────────────────────
    username: str = ""
    password: str = ""

    # ── Umum ─────────────────────────────────────────────────────────────────
    npwp:       str = "0741325344011000"
    masa_pajak: str = "Maret 2026"
    max_pages:  Optional[int] = None


class JobStatus(BaseModel):
    job_id:     str
    status:     str   # pending | running | waiting_captcha | done | error
    total:      int
    downloaded: int
    failed:     int
    message:    str
    zip_ready:  bool


class CaptchaSubmit(BaseModel):
    code: str


# ─── Helper ──────────────────────────────────────────────────────────────────
def _job_dir(job_id: str) -> Path:
    d = DOWNLOAD_DIR / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _update_job(job_id: str, **kwargs):
    if job_id in jobs:
        jobs[job_id].update(kwargs)


def _public_job(job_id: str) -> dict:
    """Kembalikan data job tanpa field internal (_captcha_*)."""
    j = jobs[job_id]
    return {k: v for k, v in j.items() if not k.startswith("_")}


# ─── Core Playwright automation ───────────────────────────────────────────────
async def _run_download_job(job_id: str, req: StartJobRequest):
    if not PLAYWRIGHT_AVAILABLE:
        _update_job(job_id, status="error",
                    message="Playwright tidak terinstall. Jalankan: pip install playwright && playwright install chromium")
        return

    out_dir = _job_dir(job_id)
    _update_job(job_id, status="running", message="Membuka browser…")

    use_cookie_mode = bool(req.cookie_string and req.cookie_string.strip())

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        try:

            # ══════════════════════════════════════════════════════════════════
            # MODE 1: COOKIE — skip login, langsung ke halaman issued
            # ══════════════════════════════════════════════════════════════════
            if use_cookie_mode:
                _update_job(job_id, message="Mode cookie: menyiapkan sesi browser…")

                # Parse cookie string → list of dicts untuk Playwright
                parsed_cookies = []
                for part in req.cookie_string.strip().split(";"):
                    part = part.strip()
                    if "=" in part:
                        name, _, value = part.partition("=")
                        parsed_cookies.append({
                            "name":   name.strip(),
                            "value":  value.strip(),
                            "domain": "coretaxdjp.pajak.go.id",
                            "path":   "/",
                        })

                if not parsed_cookies:
                    raise RuntimeError(
                        "Cookie string tidak valid. Pastikan format: 'nama1=nilai1; nama2=nilai2; ...'"
                    )

                await context.add_cookies(parsed_cookies)
                _update_job(job_id, message=f"{len(parsed_cookies)} cookie di-set. Membuka halaman eBupot…")

                # Langsung buka halaman issued — lewati seluruh flow login
                await page.goto(ISSUED_URL, timeout=60_000)
                await page.wait_for_load_state("networkidle", timeout=30_000)
                await asyncio.sleep(2)

                current_url = page.url
                if "login" in current_url.lower() or "identityprovider" in current_url.lower():
                    await page.screenshot(path=str(out_dir / "debug_cookie_redirect.png"))
                    raise RuntimeError(
                        "Cookie kedaluwarsa atau tidak valid — browser diredirect ke halaman login. "
                        "Silakan login ulang di browser Chrome, copy cookie baru, lalu coba lagi."
                    )

                _update_job(job_id, message=f"Sesi valid ✓  Membuka tabel eBupot BPU…")
                await page.screenshot(path=str(out_dir / "debug_issued_page.png"))

            # ══════════════════════════════════════════════════════════════════
            # MODE 2: LOGIN OTOMATIS (username + password + CAPTCHA)
            # ══════════════════════════════════════════════════════════════════
            else:
                if not req.username or not req.password:
                    raise RuntimeError(
                        "Isi cookie_string (mode cookie) ATAU username+password (mode login)."
                    )

                # ── 1. Buka halaman login ─────────────────────────────────────
                _update_job(job_id, message="Membuka halaman login Coretax…")
                await page.goto(LOGIN_URL, timeout=60_000)
                await page.wait_for_load_state("networkidle", timeout=30_000)
                await asyncio.sleep(1.5)

                # ── 2. Screenshot CAPTCHA → pause, tunggu user input ───────────
                captcha_path = out_dir / "captcha.png"
                CAPTCHA_IMG_SELECTORS = [
                    'img[src*="Captcha"]', 'img[src*="captcha"]',
                    'img[id*="captcha" i]', 'img[class*="captcha" i]',
                    'canvas[id*="captcha" i]', '#captchaImage',
                    '.captcha img', 'div[class*="captcha"] img',
                ]
                captcha_isolated = False
                for csel in CAPTCHA_IMG_SELECTORS:
                    try:
                        cimg = page.locator(csel).first
                        if await cimg.is_visible(timeout=2_000):
                            await cimg.screenshot(path=str(captcha_path))
                            captcha_isolated = True
                            break
                    except Exception:
                        continue

                if not captcha_isolated:
                    try:
                        form_loc = page.locator(
                            "form, .login-form, .login-container, div:has(input[type='password'])"
                        ).first
                        if await form_loc.is_visible(timeout=3_000):
                            await form_loc.screenshot(path=str(captcha_path))
                        else:
                            await page.screenshot(path=str(captcha_path))
                    except Exception:
                        await page.screenshot(path=str(captcha_path))

                await page.screenshot(path=str(out_dir / "debug_login_fullpage.png"))

                captcha_event: asyncio.Event = jobs[job_id]["_captcha_event"]
                _update_job(job_id, status="waiting_captcha",
                            message="Silakan lihat gambar CAPTCHA dan isi kode di bawah, lalu klik Submit.")
                await captcha_event.wait()
                captcha_code: str = jobs[job_id].get("_captcha_code", "")

                # ── 3. Isi form login ──────────────────────────────────────────
                _update_job(job_id, status="running", message="Mengisi form login…")
                await page.screenshot(path=str(out_dir / "debug_before_fill.png"))

                # Dump input fields untuk diagnostik
                try:
                    all_inputs = await page.evaluate("""() =>
                        Array.from(document.querySelectorAll('input')).map(el => ({
                            type: el.type, name: el.name, id: el.id,
                            visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
                        }))
                    """)
                    summary = " | ".join(
                        f"{i['type']}[{i['name'] or i['id']}]"
                        for i in all_inputs if i.get("visible")
                    )
                    _update_job(job_id, message=f"Input fields: {summary}")
                except Exception:
                    pass

                async def fill_field(selectors: list[str], value: str, label: str) -> str:
                    for sel in selectors:
                        try:
                            loc = page.locator(sel).first
                            if await loc.is_visible(timeout=2_000):
                                await loc.click()
                                await loc.fill("")
                                await loc.press_sequentially(value, delay=40)
                                await page.evaluate(
                                    "(el) => { el.dispatchEvent(new Event('input',{bubbles:true}));"
                                    " el.dispatchEvent(new Event('change',{bubbles:true})); }",
                                    await loc.element_handle()
                                )
                                return sel
                        except Exception:
                            continue
                    await page.screenshot(path=str(out_dir / f"debug_no_{label}.png"))
                    raise RuntimeError(f"Field '{label}' tidak ditemukan. Cek screenshot debug_no_{label}.png")

                await fill_field([
                    'input[name="UserName"]', 'input[id="UserName"]',
                    'input[name="username"]', 'input[id="username"]',
                    'input[autocomplete="username"]',
                    'input[placeholder*="ID Pengguna"]', 'input[placeholder*="NPWP"]',
                    'input[type="text"]:visible',
                ], req.username, "username")

                await fill_field([
                    'input[name="Password"]', 'input[id="Password"]',
                    'input[name="password"]', 'input[id="password"]',
                    'input[type="password"]:visible',
                ], req.password, "password")

                await fill_field([
                    'input[name="CaptchaCode"]', 'input[id="CaptchaCode"]',
                    'input[name="captcha"]', 'input[id="captcha"]',
                    'input[name="VerificationCode"]', 'input[name="CaptchaInputText"]',
                    'input[placeholder*="CAPTCHA" i]', 'input[placeholder*="kode" i]',
                ], captcha_code, "captcha")

                await page.screenshot(path=str(out_dir / "debug_form_filled.png"))
                _update_job(job_id, message="Form terisi, submit login…")

                # ── 4. Submit form ─────────────────────────────────────────────
                SUBMIT_SELECTORS = [
                    'input[type="submit"][value="Login"]',
                    'button[type="submit"]:has-text("Login")',
                    'button:has-text("Login")',
                    'button[type="submit"]',
                    'input[type="submit"]',
                ]
                submitted = False
                for sel in SUBMIT_SELECTORS:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=2_000):
                            await btn.click()
                            submitted = True
                            break
                    except Exception:
                        continue
                if not submitted:
                    await page.screenshot(path=str(out_dir / "debug_no_submit.png"))
                    raise RuntimeError("Tombol Login tidak ditemukan. Cek debug_no_submit.png")

                # ── 5. Tunggu redirect keluar dari halaman login ───────────────
                try:
                    await page.wait_for_url(
                        lambda url: "identityproviderportal" not in url,
                        timeout=30_000,
                    )
                except PWTimeout:
                    await page.screenshot(path=str(out_dir / "debug_after_submit.png"))
                    err_text = ""
                    try:
                        err_loc = page.locator(
                            '.validation-summary-errors, [class*="error" i], '
                            '[class*="alert" i], span.field-validation-error'
                        ).first
                        if await err_loc.is_visible(timeout=2_000):
                            err_text = (await err_loc.text_content() or "").strip()[:150]
                    except Exception:
                        pass
                    hint = f' Pesan server: "{err_text}"' if err_text else ""
                    raise RuntimeError(
                        f"Login gagal — halaman tidak redirect.{hint} "
                        "Lihat debug_after_submit.png dan debug_form_filled.png di panel Debug."
                    )

                _update_job(job_id, message="Login berhasil, memilih NPWP perusahaan…")
                await asyncio.sleep(2)

                # ── 6. Pilih NPWP perusahaan (impersonation) ──────────────────
                try:
                    DROPDOWN_TRIGGERS = [
                        f'button:has-text("{req.username}")',
                        f'span:has-text("{req.username}")',
                        '[class*="account-switcher"]',
                        '[class*="user-menu"]',
                        '[class*="dropdown"]:has-text("NPWP")',
                    ]
                    dropdown_opened = False
                    for sel in DROPDOWN_TRIGGERS:
                        try:
                            trg = page.locator(sel).first
                            if await trg.is_visible(timeout=3_000):
                                await trg.click()
                                dropdown_opened = True
                                break
                        except Exception:
                            continue

                    if dropdown_opened:
                        await asyncio.sleep(0.8)
                        npwp_option = page.locator(f'*:has-text("{req.npwp}"):visible').first
                        if await npwp_option.is_visible(timeout=5_000):
                            await npwp_option.click()
                            await asyncio.sleep(2)
                            _update_job(job_id, message=f"NPWP {req.npwp} dipilih.")
                        else:
                            _update_job(job_id, message=f"Warning: Opsi NPWP {req.npwp} tidak ditemukan, lanjut.")
                    else:
                        _update_job(job_id, message="Warning: Dropdown NPWP tidak ditemukan, lanjut.")
                except Exception as e:
                    _update_job(job_id, message=f"Warning: Gagal switch NPWP ({str(e)[:60]}), lanjut…")

                # ── 7. Navigasi ke halaman eBupot BPU Issued ──────────────────
                _update_job(job_id, message="Membuka halaman eBupot BPU Issued…")
                await page.goto(ISSUED_URL, timeout=30_000)
                await page.wait_for_load_state("networkidle", timeout=30_000)
                await asyncio.sleep(2)
                await page.screenshot(path=str(out_dir / "debug_issued_page.png"))

            # ══════════════════════════════════════════════════════════════════
            # COMMON: Download semua PDF (kedua mode masuk ke sini)
            # ══════════════════════════════════════════════════════════════════

            # ── Set rows per page ke 100 ──────────────────────────────────────
            try:
                rows_dropdown = page.locator(
                    'select[title*="rows"], select[aria-label*="rows"], '
                    'select[title*="per page"], .p-paginator-rpp-options'
                ).first
                if await rows_dropdown.is_visible(timeout=3_000):
                    await rows_dropdown.select_option("100")
                    await asyncio.sleep(1.5)
            except Exception:
                pass

            # ── Filter masa pajak ─────────────────────────────────────────────
            _update_job(job_id, message=f"Filter masa pajak: {req.masa_pajak}…")
            try:
                masa_filter = page.locator(
                    'th:has-text("Masa Pajak") select, '
                    'select[aria-label*="Masa Pajak"], '
                    '.p-column-filter:has(th:has-text("Masa")) select'
                ).first
                if await masa_filter.is_visible(timeout=5_000):
                    await masa_filter.select_option(label=req.masa_pajak)
                    await asyncio.sleep(2)
                else:
                    header = page.locator('th:has-text("Masa Pajak")').first
                    if await header.is_visible(timeout=3_000):
                        await header.click()
                        await asyncio.sleep(0.5)
                        await page.get_by_text(req.masa_pajak, exact=True).first.click(timeout=5_000)
                        await asyncio.sleep(1.5)
            except Exception:
                _update_job(job_id, message="Warning: Filter masa pajak tidak bisa diset, lanjut semua data")

            # ── Download per halaman ──────────────────────────────────────────
            downloaded = 0
            failed = 0
            page_num = 1

            while True:
                await page.wait_for_load_state("networkidle", timeout=20_000)
                await asyncio.sleep(1)
                await page.screenshot(path=str(out_dir / f"debug_page_{page_num:03d}.png"))

                pdf_buttons = await page.locator(
                    'button[title="PDF"], button[aria-label="PDF"], '
                    'a[title="PDF"], button[title*="Unduh"], button[title*="Download"], '
                    'button[title*="unduh"], span.pi-file-pdf, i.pi-file-pdf, '
                    '[class*="pdf"]:visible, tbody tr td:first-child button'
                ).all()

                if not pdf_buttons:
                    await page.screenshot(path=str(out_dir / f"debug_no_pdf_btn_page{page_num}.png"))
                    _update_job(job_id,
                                message=f"Halaman {page_num}: Tidak ada tombol PDF. "
                                        f"Cek debug_no_pdf_btn_page{page_num}.png")
                    break

                _update_job(job_id, message=f"Halaman {page_num}: {len(pdf_buttons)} file, mulai download…")

                for idx, btn in enumerate(pdf_buttons):
                    try:
                        async with page.expect_download(timeout=60_000) as dl_info:
                            await btn.click()
                        dl = await dl_info.value
                        fname = dl.suggested_filename or f"ebupot_{job_id}_{downloaded+1:04d}.pdf"
                        await dl.save_as(out_dir / fname)
                        downloaded += 1
                        _update_job(job_id, downloaded=downloaded, failed=failed,
                                    message=f"Hal.{page_num} — {downloaded} file diunduh…")
                        await asyncio.sleep(0.8)
                    except Exception as e:
                        failed += 1
                        _update_job(job_id, downloaded=downloaded, failed=failed,
                                    message=f"Gagal baris {idx+1} hal.{page_num}: {str(e)[:80]}")

                if req.max_pages and page_num >= req.max_pages:
                    break

                try:
                    next_btn = page.locator(
                        'button[aria-label="Next Page"], .p-paginator-next:not(.p-disabled), '
                        'button.p-paginator-next, button:has-text("›"):not(:disabled)'
                    ).first
                    if await next_btn.is_visible(timeout=3_000) and await next_btn.is_enabled():
                        await next_btn.click()
                        page_num += 1
                        await asyncio.sleep(2)
                    else:
                        break
                except Exception:
                    break

            # ── Buat ZIP ──────────────────────────────────────────────────────
            _update_job(job_id, message=f"Download selesai. Membuat ZIP dari {downloaded} file…")
            zip_path = DOWNLOAD_DIR / f"{job_id}.zip"
            pdf_files = list(out_dir.glob("*.pdf"))

            if pdf_files:
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for pdf in pdf_files:
                        zf.write(pdf, pdf.name)
                zip_ready = True
            else:
                zip_ready = False

            _update_job(job_id,
                        status="done",
                        downloaded=downloaded,
                        failed=failed,
                        zip_ready=zip_ready,
                        message=f"Selesai! {downloaded} berhasil, {failed} gagal."
                                + (" ZIP siap didownload." if zip_ready else " Tidak ada PDF yang berhasil."))

        except Exception as e:
            _update_job(job_id, status="error", message=f"Error: {str(e)}")
        finally:
            await browser.close()


# ─── Endpoints ────────────────────────────────────────────────────────────────

@coretax_router.post("/start", response_model=JobStatus)
async def start_job(req: StartJobRequest, background_tasks: BackgroundTasks):
    """Mulai job download eBupot BPU."""
    job_id = f"job_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    jobs[job_id] = {
        "job_id":         job_id,
        "status":         "pending",
        "total":          0,
        "downloaded":     0,
        "failed":         0,
        "message":        "Job dibuat, menunggu eksekusi…",
        "zip_ready":      False,
        "_captcha_event": asyncio.Event(),
        "_captcha_code":  None,
    }
    background_tasks.add_task(_run_download_job, job_id, req)
    return _public_job(job_id)


@coretax_router.get("/status/{job_id}", response_model=JobStatus)
async def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    return _public_job(job_id)


@coretax_router.get("/captcha-image/{job_id}")
async def get_captcha_image(job_id: str):
    """Kembalikan gambar CAPTCHA sebagai PNG."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    img_path = DOWNLOAD_DIR / job_id / "captcha.png"
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Gambar CAPTCHA belum tersedia")
    return FileResponse(path=str(img_path), media_type="image/png",
                        headers={"Cache-Control": "no-store"})


@coretax_router.post("/captcha/{job_id}")
async def submit_captcha(job_id: str, body: CaptchaSubmit):
    """Kirim kode CAPTCHA. Background task akan lanjut otomatis."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    if jobs[job_id].get("status") != "waiting_captcha":
        raise HTTPException(status_code=400, detail="Job tidak sedang menunggu CAPTCHA")
    if not body.code.strip():
        raise HTTPException(status_code=400, detail="Kode CAPTCHA tidak boleh kosong")
    jobs[job_id]["_captcha_code"] = body.code.strip()
    jobs[job_id]["_captcha_event"].set()
    return {"message": "CAPTCHA diterima, proses dilanjutkan"}


@coretax_router.get("/download/{job_id}")
async def download_zip(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    if not jobs[job_id].get("zip_ready"):
        raise HTTPException(status_code=400, detail="ZIP belum siap")
    zip_path = DOWNLOAD_DIR / f"{job_id}.zip"
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="File ZIP tidak ditemukan di server")
    return FileResponse(path=str(zip_path), media_type="application/zip",
                        filename=f"ebupot_bpu_{job_id}.zip")


@coretax_router.delete("/job/{job_id}")
async def delete_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    event: asyncio.Event = jobs[job_id].get("_captcha_event")
    if event and not event.is_set():
        jobs[job_id]["_captcha_code"] = ""
        event.set()
    import shutil
    out_dir = DOWNLOAD_DIR / job_id
    if out_dir.exists():
        shutil.rmtree(out_dir)
    zip_path = DOWNLOAD_DIR / f"{job_id}.zip"
    if zip_path.exists():
        zip_path.unlink()
    del jobs[job_id]
    return {"message": "Job dihapus"}


@coretax_router.get("/debug/screenshot/{job_id}/{filename}")
async def get_debug_screenshot(job_id: str, filename: str):
    """Ambil screenshot debug (hanya .png)."""
    safe_name = Path(filename).name
    if not safe_name.endswith(".png"):
        raise HTTPException(status_code=400, detail="Hanya file .png")
    img_path = DOWNLOAD_DIR / job_id / safe_name
    if not img_path.exists():
        raise HTTPException(status_code=404, detail=f"Screenshot tidak ditemukan: {safe_name}")
    return FileResponse(path=str(img_path), media_type="image/png")
