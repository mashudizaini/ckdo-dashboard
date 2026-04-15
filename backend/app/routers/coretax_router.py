"""
coretax_router.py
FastAPI router untuk bulk download eBupot BPU dari Coretax DJP.

Alur sesuai dokumen resmi:
  1. Login di /identityproviderportal/Account/Login
     → ada CAPTCHA, user harus mengisi manual
  2. Setelah login masuk ke reg-home, pilih NPWP perusahaan dari dropdown
  3. Navigasi langsung ke /withholding-slips-portal/id-ID/ebupotbpu/issued
  4. Download semua PDF per halaman, zip hasilnya

Dependency: pip install playwright fastapi python-multipart
             playwright install chromium
"""

import asyncio
import base64
import zipfile
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

try:
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

coretax_router = APIRouter(prefix="/api/coretax", tags=["Coretax"])

LOGIN_URL   = "https://coretaxdjp.pajak.go.id/identityproviderportal/Account/Login"
ISSUED_URL  = "https://coretaxdjp.pajak.go.id/withholding-slips-portal/id-ID/ebupotbpu/issued"

DOWNLOAD_DIR = Path("downloads/coretax")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ─── In-memory job store ──────────────────────────────────────────────────────
# Struktur tiap job:
#   job_id, status, total, downloaded, failed, message, zip_ready
#   _captcha_event: asyncio.Event  — untuk pause/resume saat CAPTCHA
#   _captcha_code:  str | None     — diisi oleh endpoint /captcha/{job_id}
jobs: dict[str, dict] = {}


# ─── Schema ──────────────────────────────────────────────────────────────────
class StartJobRequest(BaseModel):
    username:   str                        # ID Pengguna (NPWP pribadi / akun login)
    password:   str                        # Kata Sandi
    npwp:       str = "0741325344011000"   # NPWP perusahaan untuk impersonation
    masa_pajak: str = "Maret 2026"        # format: "Bulan YYYY"
    max_pages:  Optional[int] = None       # None = semua halaman


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

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        try:
            # ── 1. Buka halaman login ─────────────────────────────────────
            _update_job(job_id, message="Membuka halaman login Coretax…")
            await page.goto(LOGIN_URL, timeout=60_000)
            await page.wait_for_load_state("networkidle", timeout=30_000)
            await asyncio.sleep(1.5)

            # ── 2. Screenshot CAPTCHA → pause, tunggu user input ──────────
            _update_job(job_id, message="Menunggu CAPTCHA diisi…")

            # Screenshot: coba isolasi hanya elemen gambar CAPTCHA (untuk dibaca lebih jelas)
            captcha_path = out_dir / "captcha.png"
            CAPTCHA_IMG_SELECTORS = [
                'img[src*="Captcha"]',
                'img[src*="captcha"]',
                'img[id*="captcha" i]',
                'img[class*="captcha" i]',
                'canvas[id*="captcha" i]',
                '#captchaImage',
                '.captcha img',
                'div[class*="captcha"] img',
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
                # Fallback: screenshot form / full page
                try:
                    form_loc = page.locator(
                        "form, .login-form, .login-container, "
                        "div:has(input[type='password'])"
                    ).first
                    if await form_loc.is_visible(timeout=3_000):
                        await form_loc.screenshot(path=str(captcha_path))
                    else:
                        await page.screenshot(path=str(captcha_path))
                except Exception:
                    await page.screenshot(path=str(captcha_path))

            # Screenshot full page untuk referensi terpisah
            await page.screenshot(path=str(out_dir / "debug_login_fullpage.png"))

            # Set status waiting_captcha dan tunggu event
            captcha_event: asyncio.Event = jobs[job_id]["_captcha_event"]
            _update_job(job_id, status="waiting_captcha",
                        message="Silakan lihat gambar CAPTCHA dan isi kode di bawah, lalu klik Submit.")
            await captcha_event.wait()          # ← background task berhenti di sini
            captcha_code: str = jobs[job_id].get("_captcha_code", "")

            # ── 3. Isi form login ─────────────────────────────────────────
            _update_job(job_id, status="running", message="Mengisi form login…")

            # Screenshot kondisi halaman saat background task baru resume
            await page.screenshot(path=str(out_dir / "debug_before_fill.png"))

            # Selector ID Pengguna (NPWP / username)
            USERNAME_SELECTORS = [
                'input[name="UserName"]',
                'input[id="UserName"]',
                'input[name="username"]',
                'input[id="username"]',
                'input[autocomplete="username"]',
                'input[placeholder*="ID Pengguna"]',
                'input[placeholder*="NPWP"]',
                'input[placeholder*="username" i]',
                'input[type="text"]:visible',
            ]
            PASSWORD_SELECTORS = [
                'input[name="Password"]',
                'input[id="Password"]',
                'input[name="password"]',
                'input[id="password"]',
                'input[type="password"]:visible',
            ]
            CAPTCHA_SELECTORS = [
                'input[name="CaptchaCode"]',
                'input[id="CaptchaCode"]',
                'input[name="captcha"]',
                'input[id="captcha"]',
                'input[name="VerificationCode"]',
                'input[placeholder*="CAPTCHA" i]',
                'input[placeholder*="kode" i]',
                # Fallback: input text ketiga di form
            ]

            async def fill_first_visible(selectors: list[str], value: str, label: str) -> str:
                for sel in selectors:
                    try:
                        loc = page.locator(sel).first
                        if await loc.is_visible(timeout=2_000):
                            await loc.clear()
                            await loc.fill(value)
                            return sel
                    except Exception:
                        continue
                await page.screenshot(path=str(out_dir / f"debug_no_{label}.png"))
                raise RuntimeError(
                    f"Field '{label}' tidak ditemukan di halaman Coretax. "
                    f"Cek screenshot debug_no_{label}.png untuk melihat kondisi halaman."
                )

            used = await fill_first_visible(USERNAME_SELECTORS, req.username, "username")
            _update_job(job_id, message=f"Username diisi ({used})")

            await fill_first_visible(PASSWORD_SELECTORS, req.password, "password")
            _update_job(job_id, message="Password diisi, mengisi CAPTCHA…")

            await fill_first_visible(CAPTCHA_SELECTORS, captcha_code, "captcha")

            # Screenshot setelah semua field terisi — untuk verifikasi
            await page.screenshot(path=str(out_dir / "debug_form_filled.png"))
            _update_job(job_id, message="Form terisi, submit login…")

            # ── 4. Submit form ────────────────────────────────────────────
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
                raise RuntimeError("Tombol Login tidak ditemukan. Cek screenshot debug_no_submit.png.")

            # Tunggu redirect keluar dari halaman login
            try:
                await page.wait_for_url(
                    lambda url: "identityproviderportal" not in url,
                    timeout=30_000,
                )
            except PWTimeout:
                await page.screenshot(path=str(out_dir / "debug_after_submit.png"))
                # Coba ambil pesan error dari halaman
                err_text = ""
                try:
                    err_loc = page.locator(
                        '.validation-summary-errors, .validation-summary-valid, '
                        '[class*="error" i], [class*="alert" i], '
                        '[class*="invalid" i], span.field-validation-error'
                    ).first
                    if await err_loc.is_visible(timeout=2_000):
                        err_text = (await err_loc.text_content() or "").strip()[:150]
                except Exception:
                    pass
                hint = f' Pesan dari server: "{err_text}"' if err_text else ""
                raise RuntimeError(
                    f"Login gagal — halaman tidak redirect.{hint} "
                    f"Lihat screenshot debug_after_submit.png dan debug_form_filled.png "
                    f"di panel Debug di bawah."
                )

            _update_job(job_id, message="Login berhasil, memilih NPWP perusahaan…")
            await asyncio.sleep(2)

            # ── 5. Pilih NPWP perusahaan (impersonation) ──────────────────
            # Setelah login, user berada di reg-home dengan akun pribadi.
            # Perlu klik dropdown kanan atas → pilih NPWP perusahaan.
            try:
                # Dropdown trigger biasanya menampilkan NPWP/nama akun di kanan atas
                DROPDOWN_TRIGGER_SELECTORS = [
                    f'button:has-text("{req.username}")',
                    f'span:has-text("{req.username}")',
                    '[class*="account-switcher"]',
                    '[class*="user-menu"]',
                    '[class*="dropdown"]:has-text("NPWP")',
                    # fallback: elemen kanan atas yang berisi NPWP
                    f'*:has-text("{req.username}"):visible',
                ]
                dropdown_opened = False
                for sel in DROPDOWN_TRIGGER_SELECTORS:
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
                    # Pilih opsi yang mengandung NPWP perusahaan
                    npwp_option = page.locator(f'*:has-text("{req.npwp}"):visible').first
                    if await npwp_option.is_visible(timeout=5_000):
                        await npwp_option.click()
                        await asyncio.sleep(2)
                        _update_job(job_id, message=f"NPWP {req.npwp} dipilih, navigasi ke eBupot…")
                    else:
                        _update_job(job_id, message=f"Warning: Opsi NPWP {req.npwp} tidak ditemukan, lanjut dengan akun saat ini")
                else:
                    _update_job(job_id, message="Warning: Dropdown NPWP tidak ditemukan, lanjut tanpa switching")

            except Exception as e:
                _update_job(job_id, message=f"Warning: Gagal switch NPWP ({str(e)[:60]}), lanjut…")

            # ── 6. Navigasi ke halaman eBupot BPU Issued ─────────────────
            _update_job(job_id, message="Membuka halaman eBupot BPU Issued…")
            await page.goto(ISSUED_URL, timeout=30_000)
            await page.wait_for_load_state("networkidle", timeout=30_000)
            await asyncio.sleep(2)

            # Screenshot halaman issued untuk debug
            await page.screenshot(path=str(out_dir / "debug_issued_page.png"))

            # ── 7. Set rows per page ke 100 agar sedikit pagination ───────
            try:
                rows_dropdown = page.locator(
                    'select[title*="rows"], select[aria-label*="rows"], '
                    'select[title*="per page"], .p-paginator-rpp-options'
                ).first
                if await rows_dropdown.is_visible(timeout=3_000):
                    await rows_dropdown.select_option("100")
                    await asyncio.sleep(1.5)
            except Exception:
                pass  # Tidak masalah jika tidak bisa ganti rows per page

            # ── 8. Filter masa pajak ──────────────────────────────────────
            _update_job(job_id, message=f"Filter masa pajak: {req.masa_pajak}…")
            try:
                # Dropdown filter Masa Pajak di header kolom atau filter panel
                masa_filter = page.locator(
                    'th:has-text("Masa Pajak") select, '
                    'select[aria-label*="Masa Pajak"], '
                    'div[aria-label*="Masa Pajak"] input, '
                    '.p-column-filter:has(th:has-text("Masa")) select'
                ).first
                if await masa_filter.is_visible(timeout=5_000):
                    await masa_filter.select_option(label=req.masa_pajak)
                    await asyncio.sleep(2)
                else:
                    # Coba klik header kolom → dropdown filter muncul
                    header = page.locator('th:has-text("Masa Pajak")').first
                    if await header.is_visible(timeout=3_000):
                        await header.click()
                        await asyncio.sleep(0.5)
                        await page.get_by_text(req.masa_pajak, exact=True).first.click(timeout=5_000)
                        await asyncio.sleep(1.5)
            except Exception:
                _update_job(job_id, message=f"Warning: Filter masa pajak tidak bisa diset otomatis, lanjut dengan semua data")

            # ── 9. Download semua PDF per halaman ─────────────────────────
            downloaded = 0
            failed = 0
            page_num = 1

            while True:
                await page.wait_for_load_state("networkidle", timeout=20_000)
                await asyncio.sleep(1)

                # Screenshot per halaman untuk referensi
                await page.screenshot(path=str(out_dir / f"debug_page_{page_num:03d}.png"))

                # Tombol PDF per baris: Coretax menggunakan icon button di tiap row
                # Biasanya berupa button dengan icon PDF, atau tombol ke-2/ke-3 di kolom aksi
                pdf_buttons = await page.locator(
                    # Berbagai kemungkinan selector tombol PDF di tabel Coretax
                    'button[title="PDF"], '
                    'button[aria-label="PDF"], '
                    'a[title="PDF"], '
                    'button[title*="Unduh"], '
                    'button[title*="Download"], '
                    'button[title*="unduh"], '
                    'span.pi-file-pdf, '              # PrimeNG icon
                    'i.pi-file-pdf, '
                    '[class*="pdf"]:visible, '
                    # Fallback: semua tombol di kolom paling kiri setiap row
                    'tbody tr td:first-child button'
                ).all()

                if not pdf_buttons:
                    # Screenshot untuk membantu identifikasi selector yang benar
                    await page.screenshot(path=str(out_dir / f"debug_no_pdf_btn_page{page_num}.png"))
                    _update_job(job_id,
                                message=f"Halaman {page_num}: Tidak ada tombol PDF. "
                                        f"Cek screenshot debug_no_pdf_btn_page{page_num}.png")
                    break

                _update_job(job_id,
                            message=f"Halaman {page_num}: {len(pdf_buttons)} file ditemukan, mulai download…")

                for idx, btn in enumerate(pdf_buttons):
                    try:
                        async with page.expect_download(timeout=60_000) as dl_info:
                            await btn.click()
                        dl = await dl_info.value
                        fname = dl.suggested_filename or f"ebupot_{job_id}_{downloaded+1:04d}.pdf"
                        save_path = out_dir / fname
                        await dl.save_as(save_path)
                        downloaded += 1
                        _update_job(job_id, downloaded=downloaded, failed=failed,
                                    message=f"Halaman {page_num} — {downloaded} file diunduh…")
                        await asyncio.sleep(0.8)

                    except Exception as e:
                        failed += 1
                        _update_job(job_id, downloaded=downloaded, failed=failed,
                                    message=f"Gagal download baris {idx+1} hal.{page_num}: {str(e)[:80]}")

                # Cek limit halaman
                if req.max_pages and page_num >= req.max_pages:
                    break

                # Cek tombol Next
                try:
                    next_btn = page.locator(
                        'button[aria-label="Next Page"], '
                        '.p-paginator-next:not(.p-disabled), '
                        'button.p-paginator-next, '
                        'button:has-text("›"):not(:disabled), '
                        '[data-testid="next-page"]'
                    ).first
                    if await next_btn.is_visible(timeout=3_000) and await next_btn.is_enabled():
                        await next_btn.click()
                        page_num += 1
                        await asyncio.sleep(2)
                    else:
                        break
                except Exception:
                    break

            # ── 10. Buat ZIP ──────────────────────────────────────────────
            _update_job(job_id, message=f"Selesai download. Membuat file ZIP dari {downloaded} file…")
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
    """Mulai job download. Status akan jadi 'waiting_captcha' — client harus ambil
    gambar CAPTCHA, isi kodenya, lalu POST ke /captcha/{job_id}."""
    job_id = f"job_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    jobs[job_id] = {
        "job_id":         job_id,
        "status":         "pending",
        "total":          0,
        "downloaded":     0,
        "failed":         0,
        "message":        "Job dibuat, menunggu eksekusi…",
        "zip_ready":      False,
        # Internal — tidak dikirim ke client
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
    """Kembalikan gambar CAPTCHA sebagai PNG (langsung ditampilkan di browser / <img>)."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    img_path = DOWNLOAD_DIR / job_id / "captcha.png"
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Gambar CAPTCHA belum tersedia, tunggu sebentar")
    return FileResponse(path=str(img_path), media_type="image/png",
                        headers={"Cache-Control": "no-store"})


@coretax_router.post("/captcha/{job_id}")
async def submit_captcha(job_id: str, body: CaptchaSubmit):
    """Kirim kode CAPTCHA yang diisi user. Background task akan lanjut otomatis."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    if jobs[job_id].get("status") != "waiting_captcha":
        raise HTTPException(status_code=400, detail="Job tidak sedang menunggu CAPTCHA")
    if not body.code.strip():
        raise HTTPException(status_code=400, detail="Kode CAPTCHA tidak boleh kosong")

    jobs[job_id]["_captcha_code"] = body.code.strip()
    jobs[job_id]["_captcha_event"].set()   # resume background task
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

    # Kalau job masih waiting_captcha, fire event agar background task tidak stuck
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
