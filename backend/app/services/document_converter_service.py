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
recognition per page, not just text extraction). This used to matter for
request-timeout reasons when conversion ran inline in an SSE-streamed HTTP
request; now that it runs as a Celery background task
(app/tasks/document_converter_tasks.py) with progress polled from a DB row
instead of streamed, there's no HTTP connection to time out — the per-page
split here just gives that task a natural point to update progress after
each page instead of blocking silently for the whole document.
"""
from docling.document_converter import DocumentConverter

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg"}


def convert_one(converter: DocumentConverter, path: str) -> str:
    result = converter.convert(path)
    return result.document.export_to_markdown()
