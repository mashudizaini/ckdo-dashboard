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

Language / OCR engine: the default DocumentConverter() uses docling's
default OCR engine, RapidOCR, which per docling's own OCR options
reference does NOT actually support language selection — its `lang` field
is "reserved for future compatibility" and it's tuned for English/Chinese.
For a document in a script RapidOCR doesn't really read (e.g. Korean),
build_converter() below swaps in TesseractCliOcrOptions instead, which
shells out to the same system `tesseract` binary the Knowledge Base's
plain-OCR fallback already uses (see chatbot.py) — no new dependency,
just the matching `tesseract-ocr-<code>` language pack in the Dockerfile.
Add a new language by adding both.
"""
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TesseractCliOcrOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg"}

# language (as sent by the frontend / stored on the job) -> Tesseract
# 3-letter ISO 639-2 language codes to OCR with, English kept alongside
# every non-English pack since real documents are rarely purely
# single-language (headers/footers, mixed terms, page numbers, ...).
# "auto" (or anything unrecognized) falls through to the default RapidOCR
# pipeline in build_converter() below — unchanged from before this option
# existed.
OCR_LANGUAGE_PACKS = {
    "korean": ["kor", "eng"],
}


def build_converter(language: str = "auto") -> DocumentConverter:
    packs = OCR_LANGUAGE_PACKS.get(language)
    if not packs:
        return DocumentConverter()

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True
    pipeline_options.ocr_options = TesseractCliOcrOptions(lang=packs)
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)})


def convert_one(converter: DocumentConverter, path: str) -> str:
    result = converter.convert(path)
    return result.document.export_to_markdown()
