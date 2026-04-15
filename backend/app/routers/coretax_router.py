"""
coretax_router.py
FastAPI router untuk bulk download eBupot BPU dari Coretax DJP.
Tambahkan ke main FastAPI app dengan: app.include_router(coretax_router)

Dependency: pip install playwright fastapi python-multipart
             playwright install chromium
"""

import asyncio
import os
import zipfile
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Playwright diimport secara lazy agar tidak crash jika belum terinstall
try:
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

coretax_router = APIRouter(prefix="/api/coretax", tags=["Coretax"])

# ─── Direktori output ────────────────────────────────────────────────────────
DOWNLOAD_DIR = Path("downloads/coretax")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ─── In-memory job store (ganti Redis/DB jika perlu persistent) ──────────────
jobs: dict[str, dict] = {}


# ─── Schema ──────────────────────────────────────────────────────────────────
class StartJobRequest(BaseModel):
    username: str
    password: str
    npwp: str = "0741325344011000"
    masa_pajak: str = "Maret 2026"   # format: "Bulan YYYY"
    max_pages: Optional[int] = None  # None = semua halaman


class JobStatus(BaseModel):
    job_id: str
    status: str          # pending | running | done | error
    total: int
    downloaded: int
    failed: int
    message: str
    zip_ready: bool


# ─── Helper ──────────────────────────────────────────────────────────────────
def _job_dir(job_id: str) -> Path:
    d = DOWNLOAD_DIR / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _update_job(job_id: str, **kwargs):
    if job_id in jobs:
        jobs[job_id].update(kwargs)


# ─── Core Playwright automation ───────────────────────────────────────────────
async def _run_download_job(job_id: str, req: StartJobRequest):
    if not PLAYWRIGHT_AVAILABLE:
        _update_job(job_id, status="error", message="Playwright tidak terinstall. Jalankan: pip install playwright && playwright install chromium")
        return

    out_dir = _job_dir(job_id)
    _update_job(job_id, status="running", message="Membuka browser…")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        try:
            # ── 1. Login ──────────────────────────────────────────────────
            _update_job(job_id, message="Login ke Coretax…")
            await page.goto("https://coretaxdjp.pajak.go.id/", timeout=60_000)

            # Isi form login (sesuaikan selector jika Coretax mengubah UI)
            await page.fill('input[name="username"], input[type="text"]', req.username, timeout=15_000)
            await page.fill('input[name="password"], input[type="password"]', req.password)
            await page.click('button[type="submit"], button:has-text("Masuk"), button:has-text("Login")')

            # Tunggu redirect setelah login
            await page.wait_for_url("**/dashboard**", timeout=30_000)
            _update_job(job_id, message="Login berhasil")

            # ── 2. Navigasi ke eBupot BPU Issued ─────────────────────────
            target_url = (
                "https://coretaxdjp.pajak.go.id/withholding-slips-portal/id-ID/ebupotbpu/issued"
            )
            await page.goto(target_url, timeout=30_000)
            await page.wait_for_load_state("networkidle", timeout=30_000)

            # ── 3. Filter masa pajak ──────────────────────────────────────
            _update_job(job_id, message=f"Filter masa pajak: {req.masa_pajak}…")
            # Klik dropdown masa pajak dan pilih bulan yang diminta
            # (selector bisa berbeda; inspect elemen jika perlu)
            try:
                masa_dropdown = page.locator('div.masa-pajak-filter, [data-testid="masa-pajak"]').first
                await masa_dropdown.click(timeout=5_000)
                await page.get_by_text(req.masa_pajak, exact=True).click(timeout=5_000)
                await page.wait_for_load_state("networkidle", timeout=15_000)
            except PWTimeout:
                _update_job(job_id, message="Warning: Tidak bisa filter masa pajak otomatis, lanjut dengan data tampil saat ini")

            # ── 4. Hitung total baris ─────────────────────────────────────
            downloaded = 0
            failed = 0
            page_num = 1

            while True:
                await page.wait_for_load_state("networkidle", timeout=20_000)

                # Ambil semua tombol PDF di halaman saat ini
                # Icon PDF biasanya berupa <a> atau <button> dengan class tertentu
                pdf_buttons = await page.locator(
                    'button[title*="PDF"], a[title*="PDF"], '
                    'button.pdf-btn, [data-action="download-pdf"], '
                    'td button:nth-child(3)'   # fallback: tombol ke-3 di setiap baris
                ).all()

                if not pdf_buttons:
                    _update_job(job_id, message="Tidak ada tombol PDF ditemukan di halaman ini")
                    break

                _update_job(job_id, message=f"Halaman {page_num}: {len(pdf_buttons)} file ditemukan")

                for idx, btn in enumerate(pdf_buttons):
                    try:
                        async with page.expect_download(timeout=30_000) as dl_info:
                            await btn.click()
                        download = await dl_info.value

                        # Nama file dari suggested filename atau buat dari nomor urut
                        filename = download.suggested_filename or f"bukti_potong_{job_id}_{downloaded+1:04d}.pdf"
                        save_path = out_dir / filename
                        await download.save_as(save_path)
                        downloaded += 1
                        _update_job(job_id, downloaded=downloaded, failed=failed,
                                    message=f"Halaman {page_num} — Mengunduh {downloaded} file…")

                        # Jeda kecil agar tidak flood server
                        await asyncio.sleep(0.8)

                    except Exception as e:
                        failed += 1
                        _update_job(job_id, downloaded=downloaded, failed=failed,
                                    message=f"Gagal download baris {idx+1}: {str(e)[:80]}")

                # Cek apakah ada halaman berikutnya
                if req.max_pages and page_num >= req.max_pages:
                    break

                next_btn = page.locator('button[aria-label="Next page"], button:has-text("›"), [data-testid="next-page"]').first
                if await next_btn.is_visible() and await next_btn.is_enabled():
                    await next_btn.click()
                    page_num += 1
                    await asyncio.sleep(1.5)
                else:
                    break  # Tidak ada halaman berikutnya

            # ── 5. Zip semua PDF ──────────────────────────────────────────
            _update_job(job_id, message="Membuat file ZIP…")
            zip_path = DOWNLOAD_DIR / f"{job_id}.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for pdf in out_dir.glob("*.pdf"):
                    zf.write(pdf, pdf.name)

            _update_job(job_id,
                        status="done",
                        downloaded=downloaded,
                        failed=failed,
                        zip_ready=True,
                        message=f"Selesai! {downloaded} file berhasil, {failed} gagal.")

        except Exception as e:
            _update_job(job_id, status="error", message=f"Error: {str(e)}")
        finally:
            await browser.close()


# ─── Endpoints ────────────────────────────────────────────────────────────────

@coretax_router.post("/start", response_model=JobStatus)
async def start_job(req: StartJobRequest, background_tasks: BackgroundTasks):
    """Mulai job download bulk eBupot BPU."""
    job_id = f"job_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "total": 0,
        "downloaded": 0,
        "failed": 0,
        "message": "Job dibuat, menunggu eksekusi…",
        "zip_ready": False,
    }
    background_tasks.add_task(_run_download_job, job_id, req)
    return jobs[job_id]


@coretax_router.get("/status/{job_id}", response_model=JobStatus)
async def get_status(job_id: str):
    """Cek status job download."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    return jobs[job_id]


@coretax_router.get("/download/{job_id}")
async def download_zip(job_id: str):
    """Download file ZIP hasil bulk download."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    if not jobs[job_id].get("zip_ready"):
        raise HTTPException(status_code=400, detail="ZIP belum siap")

    zip_path = DOWNLOAD_DIR / f"{job_id}.zip"
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="File ZIP tidak ditemukan")

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=f"ebupot_bpu_{job_id}.zip",
    )


@coretax_router.delete("/job/{job_id}")
async def delete_job(job_id: str):
    """Hapus job dan file terkait."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")

    # Hapus file
    out_dir = DOWNLOAD_DIR / job_id
    if out_dir.exists():
        import shutil
        shutil.rmtree(out_dir)
    zip_path = DOWNLOAD_DIR / f"{job_id}.zip"
    if zip_path.exists():
        zip_path.unlink()

    del jobs[job_id]
    return {"message": "Job dihapus"}
