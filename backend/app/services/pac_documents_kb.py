"""
PAC document folders -> Knowledge Base text
───────────────────────────────────────────
PAC keeps its finance documents as folder trees, e.g. "01.Loan":

    Bank/<facility>/{Agreement,Drawdown,…}/…pdf|xlsx
    Shareholder/<lender>/<n-th loan>/…pdf
    Shareholder/V12.Interest Shareholder's Loan (….xlsx)

Each file becomes one Knowledge Base document, tagged PAC (so CoChat's
search_company_documents only returns it to callers whose kb_departments
include PAC). The folder path is the context a reader needs ("which loan
is this agreement for?"), so it goes into the source and the intro:

    source  "PAC Doc - Loan - Bank - 1. Investment Loan I - IDR 80bio"
            (folder label + the first two folder levels — category, facility)
    title   the rest of the path, e.g. "agreement/2024/02.Final LOI ….pdf"

Every source starts with SOURCE_PREFIX, which openwebui_sync_service uses
to keep these out of the CoChat Knowledge collection (it has no per-user
filter), the same as the Business Plan.

Formats: PDF text per page, OCR (Tesseract ind+eng, 300 dpi — same as the
Knowledge Base upload) for pages without a text layer; xlsx through
business_plan_kb's sheet parser, one paragraph per row with its column
headers; plain text. Photos, .doc (no converter in the image) and
Thumbs.db are reported and skipped. Byte-identical copies in several
folders are imported once; the intro lists the other locations.
"""
import hashlib
import os

from app.services import business_plan_kb

SOURCE_PREFIX = "PAC Doc - "
SKIP_NAMES = {"thumbs.db", "desktop.ini", ".ds_store"}
TEXT_EXT = {".pdf", ".xlsx", ".xlsm", ".txt"}
MIN_PAGE_TEXT = 50  # chars — below this a page is treated as scanned


def is_pac_doc_source(source: str) -> bool:
    return (source or "").startswith(SOURCE_PREFIX)


def source_and_title(label: str, rel_path: str) -> tuple[str, str]:
    """rel_path is relative to the imported folder, '/'-separated."""
    parts = rel_path.split("/")
    folders, name = parts[:-1], parts[-1]
    group = folders[:2]
    source = SOURCE_PREFIX + " - ".join([label] + group)
    title = "/".join(folders[2:] + [name])
    return source, title


def scan_folder(root: str) -> tuple[list[dict], list[str]]:
    """Unique importable files under root, and the skipped ones.
    Returns ([{rel, path, sha256, copies: [rel, …]}], [skipped rel])."""
    by_hash: dict[str, dict] = {}
    skipped = []
    for dirpath, _dirs, files in os.walk(root):
        for f in sorted(files):
            path = os.path.join(dirpath, f)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            ext = os.path.splitext(f)[1].lower()
            if f.lower() in SKIP_NAMES or f.startswith("~$") or ext not in TEXT_EXT:
                skipped.append(rel)
                continue
            with open(path, "rb") as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()
            if digest in by_hash:
                by_hash[digest]["copies"].append(rel)
            else:
                by_hash[digest] = {"rel": rel, "path": path, "sha256": digest, "copies": []}
    files = sorted(by_hash.values(), key=lambda d: d["rel"])
    for d in files:
        d["copies"].sort()
    return files, sorted(skipped)


# ── Extraction ───────────────────────────────────────────────────────

def _pdf_text(path: str, ocr: bool) -> tuple[str, int, int]:
    """(text, pages, pages OCR'd)."""
    import fitz
    if ocr:
        # Same override as the Knowledge Base upload: the image's baked-in
        # TESSDATA_PREFIX points at Tesseract 4's path, it ships 5.
        os.environ["TESSDATA_PREFIX"] = "/usr/share/tesseract-ocr/5/tessdata"
    doc = fitz.open(path)
    pages, ocr_pages = [], 0
    try:
        for n, page in enumerate(doc, 1):
            text = page.get_text().strip()
            if len(text) < MIN_PAGE_TEXT and ocr:
                try:
                    tp = page.get_textpage_ocr(dpi=300, language="ind+eng", full=True)
                    ocr_text = page.get_text(textpage=tp).strip()
                    if len(ocr_text) > len(text):
                        text = ocr_text
                        ocr_pages += 1
                except Exception:
                    pass
            if text:
                pages.append(f"[Halaman {n}]\n{text}")
        return "\n\n".join(pages), doc.page_count, ocr_pages
    finally:
        doc.close()


def _xlsx_text(path: str, tag: str) -> str:
    from python_calamine import CalamineWorkbook
    wb = CalamineWorkbook.from_path(path)
    out = []
    for meta in wb.sheets_metadata:
        if "hidden" in str(meta.visible).lower():
            continue
        rows = wb.get_sheet_by_name(meta.name).to_python(skip_empty_area=False)
        title, events = business_plan_kb._parse_sheet(rows)
        sheet_tag = f"[{tag} · sheet {meta.name}" + (f" · {title}" if title else "")
        for ev in events:
            if ev["kind"] == "columns":
                out.append("Kolom: " + " | ".join(ev["texts"]))
                continue
            parts = [f"{h}: {business_plan_kb._fmt(v, p)}" if h else business_plan_kb._fmt(v, p)
                     for h, v, p in ev["cells"]]
            label = " > ".join(ev["path"])
            body = f"{label} — {' · '.join(parts)}" if parts and label else (label or " · ".join(parts))
            unit = f" · {ev['unit']}" if ev["unit"] else ""
            out.append(f"{sheet_tag}{unit}] {body}")
    return "\n\n".join(out)


def file_document(label: str, item: dict, ocr: bool = True) -> dict:
    """{source, title, text, kind, pages, ocr_pages} for one scanned file."""
    rel, path = item["rel"], item["path"]
    source, title = source_and_title(label, rel)
    ext = os.path.splitext(rel)[1].lower()
    pages = ocr_pages = 0
    if ext == ".pdf":
        body, pages, ocr_pages = _pdf_text(path, ocr)
    elif ext in (".xlsx", ".xlsm"):
        body = _xlsx_text(path, f"{label} · {os.path.basename(rel)}")
    else:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            body = fh.read()
    folder = " / ".join(rel.split("/")[:-1]) or "(folder utama)"
    intro = (
        f"Dokumen PAC — {label}. Folder: {folder}. Berkas: {os.path.basename(rel)}."
        + (f" Salinan identik juga ada di: {'; '.join(item['copies'])}." if item["copies"] else "")
    )
    text = f"{intro}\n\n{body.strip()}" if body.strip() else ""
    return {"source": source, "title": title, "text": text, "kind": ext.lstrip("."),
            "pages": pages, "ocr_pages": ocr_pages}
