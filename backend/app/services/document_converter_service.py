"""
Document Converter — PDF / DOCX / image -> RAG-friendly Markdown

Uses docling (OCR via RapidOCR/onnxruntime + table-structure recognition,
CPU-only, no torch) instead of the plain Tesseract text-dump used by the
Knowledge Base's direct PDF upload. Docling reconstructs actual markdown
tables (`| col | col |`) with row labels correctly attached to their
values and clean section headings — validated empirically on a real
scanned benefit table that plain OCR text scrambled beyond usable (label
and numbers landed in the wrong order/chunk); docling produced a perfect
table on the first try.

Trade-off: much slower than plain OCR — measured ~73s/page average on a
real scanned PDF (docling runs OCR + layout analysis + table-structure
recognition per page, not just text extraction). So conversion streams
per-page progress over SSE rather than blocking until the whole document
is done — the caller can show real progress instead of a silent multi-
minute hang, and nginx's proxy_read_timeout only needs to tolerate the
gap between individual pages (~1-2 min), not the whole document.
"""
import asyncio
import json
import os
from docling.document_converter import DocumentConverter

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg"}


def _convert_one(converter: DocumentConverter, path: str) -> str:
    result = converter.convert(path)
    return result.document.export_to_markdown()


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


async def convert_stream(file_path: str, ext: str):
    """
    Async generator yielding SSE-formatted progress/result events:
      {"type": "progress", "page": i, "total": n, "message": "..."}
      {"type": "page_result", "page": i, "total": n, "markdown": "..."}
      {"type": "done", "markdown": "<full combined markdown>"}
      {"type": "error", "message": "..."}
    Terminated by "data: [DONE]\\n\\n" either way.
    """
    if ext not in SUPPORTED_EXTENSIONS:
        yield _sse({"type": "error", "message": f"Format tidak didukung: {ext}"})
        yield "data: [DONE]\n\n"
        return

    converter = DocumentConverter()

    if ext == ".pdf":
        import fitz
        try:
            doc = fitz.open(file_path)
            total = len(doc)
        except Exception as e:
            yield _sse({"type": "error", "message": f"Gagal membuka PDF: {e}"})
            yield "data: [DONE]\n\n"
            return

        md_parts = []
        for i in range(total):
            yield _sse({"type": "progress", "page": i + 1, "total": total, "message": f"Memproses halaman {i + 1} dari {total}..."})

            page_pdf_path = f"{file_path}.page{i + 1}.pdf"
            single_doc = fitz.open()
            single_doc.insert_pdf(doc, from_page=i, to_page=i)
            single_doc.save(page_pdf_path)
            single_doc.close()

            try:
                page_md = await asyncio.to_thread(_convert_one, converter, page_pdf_path)
            except Exception as e:
                yield _sse({"type": "error", "message": f"Gagal memproses halaman {i + 1}: {e}"})
                yield "data: [DONE]\n\n"
                doc.close()
                if os.path.exists(page_pdf_path):
                    os.remove(page_pdf_path)
                return
            finally:
                if os.path.exists(page_pdf_path):
                    os.remove(page_pdf_path)

            md_parts.append(page_md)
            yield _sse({"type": "page_result", "page": i + 1, "total": total, "markdown": page_md})

        doc.close()
        yield _sse({"type": "done", "markdown": "\n\n".join(md_parts)})
        yield "data: [DONE]\n\n"
        return

    # DOCX / image — no natural page concept for docling, single-shot conversion
    yield _sse({"type": "progress", "page": 1, "total": 1, "message": "Memproses dokumen..."})
    try:
        md = await asyncio.to_thread(_convert_one, converter, file_path)
    except Exception as e:
        yield _sse({"type": "error", "message": str(e)})
        yield "data: [DONE]\n\n"
        return
    yield _sse({"type": "page_result", "page": 1, "total": 1, "markdown": md})
    yield _sse({"type": "done", "markdown": md})
    yield "data: [DONE]\n\n"
