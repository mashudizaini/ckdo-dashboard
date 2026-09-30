"""
Outlook Material Service — PAC module.
Stores and retrieves the reference source files (economic reports, market
data, etc.) uploaded ahead of writing the Business Plan Outlook.

Convert stage: each file is summarized into a structured Markdown "brief"
once (convert_material), and that brief — not the raw file — is what
generate_outlook reads from on every generation. This avoids re-reading
potentially large PDFs on every regenerate (slow, expensive, and prone to
drift between runs) in favor of a compact, reusable, point-form reference.
"""
import asyncio
import os
import re
from datetime import datetime
from typing import Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.outlook_material import OutlookMaterial
from app.services.ai_service import AIService
import structlog

logger = structlog.get_logger()

_UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", "outlook_materials"
)
os.makedirs(_UPLOAD_DIR, exist_ok=True)

# Conservative cap so extracted text + prompt + output stay comfortably
# within the num_ctx window used for the local summarization call. Cloud
# models have far larger windows, so they get much more of a long report
# (IMF/OECD PDFs run 30-200 pages; the forecast tables are rarely on the
# first few pages, which is all 15k characters covers).
_MAX_EXTRACT_CHARS = 15000
_MAX_EXTRACT_CHARS_CLOUD = 60000

# Words that mark the pages worth keeping when a document has to be cut.
_KEY_TERMS = re.compile(
    r"projection|forecast|outlook|table|gdp|growth|inflation|policy rate|interest rate|"
    r"exchange rate|brent|oil|budget|apbn|rapbn|deficit|pharma|health|"
    r"proyeksi|asumsi|pertumbuhan|inflasi|nilai tukar|anggaran|belanja|kesehatan",
    re.I,
)


class OutlookMaterialService:

    def storage_path(self, filename: str) -> str:
        return os.path.join(_UPLOAD_DIR, filename)

    async def save_files(
        self,
        db: AsyncSession,
        plan_year: int,
        files: list,
        username: str,
        category: str = "material",
    ) -> dict:
        saved = []
        for file in files:
            content = await file.read()
            ext = os.path.splitext(file.filename or "")[1]
            stored_name = f"{category}_{plan_year}_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}{ext}"
            with open(self.storage_path(stored_name), "wb") as f:
                f.write(content)

            row = OutlookMaterial(
                plan_year=plan_year,
                category=category,
                filename=stored_name,
                original_name=file.filename or stored_name,
                content_type=file.content_type,
                file_size=len(content),
                uploaded_by=username,
            )
            db.add(row)
            await db.flush()
            await db.refresh(row)
            saved.append(self._to_dict(row))
        return {"success": True, "count": len(saved), "data": saved}

    async def list_materials(self, db: AsyncSession, plan_year: Optional[int] = None, category: Optional[str] = None) -> dict:
        q = select(OutlookMaterial).order_by(OutlookMaterial.created_at.desc())
        if plan_year:
            q = q.where(OutlookMaterial.plan_year == plan_year)
        if category:
            q = q.where(OutlookMaterial.category == category)
        result = await db.execute(q)
        rows = result.scalars().all()
        return {"success": True, "count": len(rows), "data": [self._to_dict(r) for r in rows]}

    async def get_material(self, db: AsyncSession, material_id: int) -> Optional[OutlookMaterial]:
        return await db.get(OutlookMaterial, material_id)

    async def delete_material(self, db: AsyncSession, material_id: int) -> dict:
        row = await db.get(OutlookMaterial, material_id)
        if not row:
            return {"success": False, "error": "Not found"}
        path = self.storage_path(row.filename)
        if os.path.exists(path):
            os.remove(path)
        await db.execute(delete(OutlookMaterial).where(OutlookMaterial.id == material_id))
        return {"success": True, "message": f"Deleted material #{material_id}"}

    # ── Convert stage ────────────────────────────────────────────────────

    def _extract_text(self, path: str, original_name: str) -> str:
        ext = os.path.splitext(original_name or path)[1].lower()

        if ext == ".pdf":
            import fitz
            doc = fitz.open(path)
            try:
                return "\n".join(f"# Page {i}\n{page.get_text()}" for i, page in enumerate(doc, start=1))
            finally:
                doc.close()

        if ext in (".docx", ".doc"):
            import docx
            d = docx.Document(path)
            return "\n".join(p.text for p in d.paragraphs)

        if ext in (".pptx", ".ppt"):
            from pptx import Presentation
            prs = Presentation(path)
            lines = []
            for i, slide in enumerate(prs.slides, start=1):
                slide_lines = []
                self._pptx_shapes_text(slide.shapes, slide_lines)
                if slide_lines:
                    lines.append(f"# Slide {i}")
                    lines.extend(slide_lines)
            return "\n".join(lines)

        if ext in (".xlsx", ".xlsm"):
            import openpyxl
            wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
            lines = []
            for ws in wb.worksheets:
                lines.append(f"# Sheet: {ws.title}")
                for row in ws.iter_rows(values_only=True):
                    vals = [str(v) for v in row if v is not None]
                    if vals:
                        lines.append(" | ".join(vals))
            return "\n".join(lines)

        if ext in (".txt", ".csv", ".md"):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()

        raise ValueError(f"Format {ext or '(tanpa ekstensi)'} belum didukung untuk convert otomatis")

    def _pptx_shapes_text(self, shapes, out: list):
        """Text, tables and chart data of a slide, in reading order (top to
        bottom, left to right). Recurses into grouped shapes — the 2026 deck
        keeps a whole section (Asia Pharmaceuticals) inside a group, which a
        flat walk silently skipped — and reads chart series, which is where
        the state-budget allocation figures live."""
        ordered = sorted(shapes, key=lambda sh: ((sh.top or 0) // 360000, sh.left or 0))
        for shape in ordered:
            if shape.shape_type == 6:  # MSO_SHAPE_TYPE.GROUP
                self._pptx_shapes_text(shape.shapes, out)
            elif getattr(shape, "has_chart", False) and shape.has_chart:
                try:
                    plot = shape.chart.plots[0]
                    out.append("[Chart] categories: " + " | ".join(str(c) for c in plot.categories))
                    for series in plot.series:
                        out.append(f"[Chart] {series.name}: " + " | ".join(
                            "" if v is None else f"{v:g}" for v in series.values))
                except Exception:
                    pass
            elif shape.has_table:
                for row in shape.table.rows:
                    cells = [c.text.replace("\n", " ").strip() for c in row.cells]
                    if any(cells):
                        out.append(" | ".join(cells))
            elif shape.has_text_frame and shape.text_frame.text.strip():
                out.append(shape.text_frame.text.strip())

    @staticmethod
    def _select_for_budget(raw_text: str, limit: int) -> tuple:
        """Fit a long document into limit characters by keeping whole
        pages/slides, preferring those dense with figures and outlook terms
        (forecast tables, budget assumptions), in their original order."""
        if len(raw_text) <= limit:
            return raw_text, False
        chunks = re.split(r"(?m)^(?=# (?:Page|Slide|Sheet)\b)", raw_text)
        if len(chunks) <= 1:
            return raw_text[:limit], True
        scored = []
        for idx, ch in enumerate(chunks):
            digits = len(re.findall(r"\d", ch))
            terms = len(_KEY_TERMS.findall(ch))
            scored.append(((digits + 20 * terms) / max(len(ch), 1), idx))
        keep, used = set(), 0
        # the opening page carries the title, date and headline summary
        if len(chunks[0]) <= limit // 10:
            keep.add(0)
            used = len(chunks[0])
        for _, idx in sorted(scored, reverse=True):
            if idx in keep or used + len(chunks[idx]) > limit:
                continue
            keep.add(idx)
            used += len(chunks[idx])
        return "".join(chunks[i] for i in sorted(keep)), True

    async def convert_material(self, db: AsyncSession, material_id: int, provider: str = "onprem", gemini_api_key: str = None) -> dict:
        """Extract text from the uploaded file and summarize it into a
        structured Markdown brief via AI — run once per file, reused on
        every Outlook generation afterwards."""
        row = await db.get(OutlookMaterial, material_id)
        if not row:
            return {"success": False, "error": "Not found"}

        row.brief_status = "converting"
        await db.flush()

        try:
            path = self.storage_path(row.filename)
            if not os.path.exists(path):
                raise FileNotFoundError("File tidak ditemukan di server")

            raw_text = await asyncio.to_thread(self._extract_text, path, row.original_name)
            raw_text = (raw_text or "").strip()
            if not raw_text:
                raise ValueError("Tidak ada teks yang bisa diekstrak dari file ini (kemungkinan hasil scan/gambar)")

            # A format example (last year's deck) is used for its exact
            # tables, labels and wording — an AI summary flattens exactly
            # that. Short enough to pass through whole, so keep it verbatim.
            if row.category == "format" and len(raw_text) <= _MAX_EXTRACT_CHARS:
                row.brief_text = raw_text
                row.brief_status = "done"
                row.brief_error = None
                row.converted_at = datetime.utcnow()
                await db.flush()
                await db.refresh(row)
                return {"success": True, "data": self._to_dict(row)}

            limit = _MAX_EXTRACT_CHARS if provider == "onprem" else _MAX_EXTRACT_CHARS_CLOUD
            text_for_ai, truncated = self._select_for_budget(raw_text, limit)
            truncation_note = "\n[...hanya halaman paling relevan yang disertakan, dokumen aslinya lebih panjang...]" if truncated else ""

            purpose = (
                "acuan STRUKTUR/FORMAT laporan Business Plan Outlook (Global Economic Outlook, "
                "Indonesia Economic Outlook, Pharmaceutical Industry) — fokus pada bagian/section "
                "apa saja yang ada dan bagaimana kontennya disusun"
                if row.category == "format" else
                "bahan sumber DATA untuk menyusun laporan Business Plan Outlook (Global Economic "
                "Outlook, Indonesia Economic Outlook, Pharmaceutical Industry)"
            )
            system = (
                "Kamu adalah analis riset yang meringkas dokumen sumber menjadi poin-poin "
                "terstruktur untuk dipakai berulang kali sebagai referensi oleh AI lain — bukan "
                "narasi panjang. Ringkasan harus padat, faktual, dan mempertahankan semua "
                "angka/statistik/tanggal penting yang ada di dokumen."
            )
            prompt = (
                f'Dokumen berikut adalah {purpose}: "{row.original_name}".\n\n'
                "Ringkas menjadi Markdown berisi poin-poin kunci saja — angka, tren, tanggal, "
                "dan fakta penting, tanpa basa-basi pembuka/penutup. Tulis dalam bahasa Inggris. "
                "Gunakan **bold** untuk angka/istilah kunci. Maksimal sekitar 35 bullet.\n"
                "Prioritaskan angka yang dipakai slide Outlook, lengkap dengan tahunnya "
                "(aktual / estimasi / proyeksi): pertumbuhan GDP per negara/kawasan (World, US, "
                "Euro area, China, Korea, Indonesia), inflasi, suku bunga kebijakan (Fed, ECB, BI), "
                "kurs (USD/IDR, USD/EUR, USD/KRW), harga minyak Brent, asumsi & alokasi APBN/RAPBN "
                "per fungsi (pangan, energi, kesehatan, pendidikan, perlindungan sosial, "
                "pertahanan), serta ukuran/pertumbuhan pasar farmasi. Jika dokumen memuat tabel "
                "proyeksi, salin sebagai tabel Markdown kecil apa adanya, jangan diparafrasekan.\n"
                "Sebut di baris pertama: nama penerbit dan bulan/tahun terbit dokumen.\n\n"
                "=== ISI DOKUMEN ===\n"
                f"{text_for_ai}{truncation_note}\n"
                "=== AKHIR DOKUMEN ==="
            )

            ai = AIService()
            brief = await ai.complete(system, prompt, provider=provider, gemini_api_key=gemini_api_key)
            brief = (brief or "").strip()
            if not brief:
                raise ValueError("AI tidak mengembalikan ringkasan (respons kosong)")

            row.brief_text = brief
            row.brief_status = "done"
            row.brief_error = None
            row.converted_at = datetime.utcnow()
        except Exception as e:
            logger.warning("outlook_material_convert_failed", material_id=material_id, error=str(e))
            row.brief_status = "failed"
            row.brief_error = str(e)[:2000]

        await db.flush()
        await db.refresh(row)
        return {"success": row.brief_status == "done", "data": self._to_dict(row)}

    def _to_dict(self, row: OutlookMaterial) -> dict:
        return {
            "id":            row.id,
            "plan_year":     row.plan_year,
            "category":      row.category,
            "original_name": row.original_name,
            "content_type":  row.content_type,
            "file_size":     row.file_size,
            "uploaded_by":   row.uploaded_by,
            "created_at":    row.created_at.isoformat() if row.created_at else None,
            "brief_status":  row.brief_status,
            "brief_text":    row.brief_text,
            "brief_error":   row.brief_error,
            "converted_at":  row.converted_at.isoformat() if row.converted_at else None,
        }
