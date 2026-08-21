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
    # `path` MUST be set explicitly — this image's baked-in TESSDATA_PREFIX
    # env var targets Tesseract 4.x's path, but the image actually ships
    # Tesseract 5.x (tessdata moved to .../5/tessdata; same quirk chatbot.py
    # already works around with `os.environ["TESSDATA_PREFIX"] = ...` for
    # its own OCR fallback). Without this, TesseractCliOcrOptions falls
    # back to the wrong env var, `tesseract` can't find kor.traineddata,
    # and its stdout isn't the TSV output docling expects — surfaces as a
    # confusing "'utf-8' codec can't decode byte ..." from docling blindly
    # decoding that stdout, not as a clear "language pack not found" error.
    pipeline_options.ocr_options = TesseractCliOcrOptions(lang=packs, path="/usr/share/tesseract-ocr/5/tessdata")
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)})


def convert_one(converter: DocumentConverter, path: str) -> str:
    result = converter.convert(path)
    return result.document.export_to_markdown()


# ── Structured extraction (blocks) ──────────────────────────────────────────
#
# Docling's own `result.document` is already structured (docling-core's
# DoclingDocument: `.tables` as TableItem objects exportable to a real 2D
# grid via `.export_to_dataframe()`, `.texts`/section headers walked via
# `.iterate_items()`) — Markdown is only ever one *serialization* of it.
# extract_blocks() walks that structure directly instead of exporting to
# Markdown and re-parsing pipe tables back out of text, so a table cell
# never gets flattened and reflowed mid-pipeline. Every render format
# (MD/DOCX/XLSX/JSONL — document_render_service.py) and the translation
# step (document_translation_service.py) both operate on this block list,
# not on Markdown text.
#
# NOTE ON RELIABILITY: iterate_items()/export_to_dataframe()'s exact
# signature was verified against docling's own published examples and
# GitHub issue tracker, not against a locally installed copy — docling
# isn't installed on the machine this was written on. If docling-core's
# API has drifted from that in the pinned docling==2.117.0, the structured
# walk below will raise and extract_blocks() falls back to deriving the
# same block shape from the (already proven, unchanged) Markdown export
# instead of breaking conversion entirely. Confirm on first real deploy
# which path is actually being taken (blocks aren't materially different
# either way for prose-only documents — it mainly matters for tables).
BlockList = list  # list[dict] — {"type": "heading", "level": int, "text": str}
                   #            | {"type": "paragraph", "text": str}
                   #            | {"type": "table", "rows": [[str, ...], ...]}


def extract_blocks(converter: DocumentConverter, path: str) -> "BlockList":
    result = converter.convert(path)
    document = result.document
    try:
        blocks = _blocks_from_structured_document(document)
        if blocks:
            return blocks
    except Exception:
        pass
    return _blocks_from_markdown(document.export_to_markdown())


def _blocks_from_structured_document(document) -> "BlockList":
    from docling_core.types.doc import TableItem, TextItem, SectionHeaderItem

    blocks: BlockList = []
    for item, _level in document.iterate_items():
        if isinstance(item, TableItem):
            df = item.export_to_dataframe(doc=document)
            rows = []
            if df is not None and not df.empty:
                rows.append([str(c) for c in df.columns])
                rows.extend(row.astype(str).tolist() for _, row in df.iterrows())
            if rows:
                blocks.append({"type": "table", "rows": rows})
        elif isinstance(item, SectionHeaderItem):
            text = (getattr(item, "text", "") or "").strip()
            if text:
                blocks.append({"type": "heading", "level": getattr(item, "level", 1) or 1, "text": text})
        elif isinstance(item, TextItem):
            text = (getattr(item, "text", "") or "").strip()
            if text:
                blocks.append({"type": "paragraph", "text": text})
    return blocks


def _blocks_from_markdown(md: str) -> "BlockList":
    """Fallback intermediate — same block shape as the structured walk
    above, derived by parsing docling's own Markdown export instead. Also
    what per-page OCR falls back to internally (see document_converter_
    tasks.py), since a scanned page's structure is thinner anyway."""
    import re

    blocks: BlockList = []
    para_buf: list[str] = []

    def flush_para():
        text = " ".join(para_buf).strip()
        if text:
            blocks.append({"type": "paragraph", "text": text})
        para_buf.clear()

    lines = md.split("\n")
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        heading_m = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if heading_m:
            flush_para()
            blocks.append({"type": "heading", "level": len(heading_m.group(1)), "text": heading_m.group(2).strip()})
            i += 1
            continue
        if stripped.startswith("|") and stripped.endswith("|") and len(stripped) > 1:
            flush_para()
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            rows = []
            for tl in table_lines:
                cells = [c.strip() for c in tl.strip("|").split("|")]
                if cells and all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                    continue  # markdown header-separator row, not real data
                rows.append(cells)
            if rows:
                blocks.append({"type": "table", "rows": rows})
            continue
        if not stripped:
            flush_para()
            i += 1
            continue
        para_buf.append(stripped)
        i += 1
    flush_para()
    return blocks


def render_markdown_from_blocks(blocks: "BlockList") -> str:
    parts = []
    for b in blocks:
        if b["type"] == "heading":
            parts.append(f"{'#' * min(max(b.get('level', 1), 1), 6)} {b['text']}")
        elif b["type"] == "paragraph":
            parts.append(b["text"])
        elif b["type"] == "table" and b.get("rows"):
            rows = b["rows"]
            header, *body = rows
            parts.append("| " + " | ".join(header) + " |")
            parts.append("|" + "|".join(["---"] * len(header)) + "|")
            for r in body:
                cells = list(r) + [""] * (len(header) - len(r))
                parts.append("| " + " | ".join(cells[:len(header)]) + " |")
    return "\n\n".join(parts)
