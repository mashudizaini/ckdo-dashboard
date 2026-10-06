"""
Business Plan workbook -> Knowledge Base text
─────────────────────────────────────────────
PAC's yearly "<year> Business plan.xlsx" is a 40–70 sheet financial model:
a numbered body (Cover, Managerial objective, 1-1 PL yearly … 10 Cashflow)
followed by an "Appendix→" divider and the raw data / calculation sheets
behind it. Only the body is meant to be read, so only the visible sheets
before that divider are converted.

Each body sheet becomes its own Knowledge Base document (one (source, title)
pair), and every row becomes one self-contained paragraph:

    [Business Plan 2026 · 1-2.PL_monthly_Summary · unit : mil Rp]
    CKD OTTO, Net Sales > Export — 2025: 80,480 · 2026(P): 96,460 · Jan: 0 · …

Why row-per-paragraph instead of a rendered table: the RAG chunker cuts on
blank lines and the retriever hands the model isolated chunks. A table cut
in half loses its header and the model can no longer tell which number is
which month. Repeating the year, sheet, unit, the row's label path and each
column's header on every row means any chunk the retriever picks is still
readable on its own.

Access: imported under the PAC tag, so CoChat's search_company_documents
only returns it to callers whose ebs_chat_scope.kb_departments include PAC.
It is also kept out of the CoChat Knowledge collection sync
(openwebui_sync_service), which copies documents without any per-user
filter.

Read with python-calamine, not openpyxl: these workbooks carry 20–45k
defined names, and openpyxl builds an object for each one before reading a
single cell (hundreds of MB, minutes). calamine reads values only.
"""
import re
from datetime import date, datetime

SOURCE_PREFIX = "Business Plan"
APPENDIX_PREFIX = "Appendix"
COMPANY_BANNER = "PT CKD OTTO"

_UNIT_RE = re.compile(r"\(\s*unit\s*:", re.I)
_YEAR_RE = re.compile(r"(20\d\d)")
_SECTION_RE = re.compile(r"^\d+(-\d+)?\.([a-z]\.?)?\s")  # "1-2. Summary…", "1-2.a Local…", "5. Investment Plan"
_MONTH_YEAR_RE = re.compile(r"^[A-Za-z]+,?\s+\d{4}$")    # the Cover's "December, 2025"
_PERCENT_HINTS = ("ratio", "%", "growth", "portion", "rate")
_IGNORED_TEXT = {">>", ">", "→"}
_MAX_PATH_DEPTH = 3


def source_for_year(year: int) -> str:
    return f"{SOURCE_PREFIX} {year}"


def is_business_plan_source(source: str) -> bool:
    return bool(re.fullmatch(rf"{SOURCE_PREFIX} 20\d\d", source or ""))


def year_from_filename(name: str) -> int | None:
    m = _YEAR_RE.search(name)
    return int(m.group(1)) if m else None


# ── Cell helpers ─────────────────────────────────────────────────────

def _clean(v):
    """Normalize one cell: whitespace-collapsed str, number, or None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, str):
        s = " ".join(v.split())
        if not s or s in _IGNORED_TEXT:
            return None
        if s.startswith("#") and (s.endswith("!") or s.endswith("A")):  # #REF!, #DIV/0!, #N/A
            return None
        return s
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, float) and v != v:  # NaN
        return None
    return v


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_year(v) -> bool:
    return _is_num(v) and float(v).is_integer() and 1990 <= v <= 2100


def _is_value_num(v) -> bool:
    """A number that is data, not a year sitting in a header row."""
    return _is_num(v) and not _is_year(v)


def _fmt_num(v, percent: bool) -> str:
    if percent and abs(v) <= 10:
        return f"{v * 100:.1f}%"
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, int):
        return f"{v:,}"
    a = abs(v)
    if a >= 1000:
        return f"{v:,.0f}"
    if a >= 100:
        return f"{v:,.1f}"
    if a >= 1:
        return f"{v:.2f}"
    return f"{v:.4g}"


def _fmt(v, percent: bool = False) -> str:
    if _is_num(v):
        return str(int(v)) if _is_year(v) else _fmt_num(v, percent)
    return str(v)


# ── Header detection ─────────────────────────────────────────────────

def _is_header_like(cells: list[tuple[int, object]], short: bool = False) -> bool:
    """short: also require every cell to be header-sized — used where no
    numbers follow to confirm it (text-only tables), so a row of prose
    like the Registration schedule's drug-timeline notes isn't taken
    for column headers."""
    if len(cells) < 3 or any(_is_value_num(v) for _, v in cells):
        return False
    return not short or all(len(_fmt(v)) <= 40 for _, v in cells)


def _build_headers(header_rows: list[list[tuple[int, object]]]) -> dict[int, str]:
    """Column -> header text. With two header rows, the top row's labels
    are spread right over the columns below them ("Monthly" over Jan…Dec,
    "2025" over its value and ratio columns) and joined with the bottom
    row's label."""
    if not header_rows:
        return {}
    last_col = max(c for row in header_rows for c, _ in row)
    per_row = []
    for i, row in enumerate(header_rows):
        cols = {c: _fmt(v) for c, v in row}
        if len(header_rows) > 1 and i < len(header_rows) - 1:
            filled, current = {}, None
            for c in range(min(cols), last_col + 1):
                current = cols.get(c, current)
                if current is not None:
                    filled[c] = current
            cols = filled
        per_row.append(cols)
    headers = {}
    for c in range(last_col + 1):
        parts = []
        for cols in per_row:
            p = cols.get(c)
            if p and p not in parts:
                parts.append(p)
        if parts:
            headers[c] = " ".join(parts)
    return headers


# ── Sheet -> paragraphs ──────────────────────────────────────────────

def _sheet_lines(rows: list[list], year: int, sheet: str) -> tuple[str, list[str]]:
    """Returns (sheet title, row paragraphs)."""
    grid = []
    for r in rows:
        cells = [(c, cv) for c, cv in ((c, _clean(v)) for c, v in enumerate(r)) if cv is not None]
        grid.append(cells)

    title = None
    unit = ""
    headers: dict[int, str] = {}
    stack: list[tuple[int, str]] = []  # (column, label) — row label hierarchy by indent column
    lines: list[str] = []
    started = False  # past the banner/title/unit preamble

    def next_nonempty(i):
        for j in range(i + 1, len(grid)):
            if grid[j]:
                return grid[j]
        return []

    i = 0
    while i < len(grid):
        cells = grid[i]
        if not cells:
            i += 1
            continue

        texts = [v for _, v in cells if isinstance(v, str)]
        unit_text = next((t for t in texts if _UNIT_RE.search(t)), None)
        if unit_text:
            unit = unit_text.strip("() ").replace("unit :", "unit:").strip()
            i += 1
            continue
        if not started:
            if texts and texts[0].upper().startswith(COMPANY_BANNER):
                i += 1
                continue
            first = cells[0][1]
            if title is None and isinstance(first, str) and not _MONTH_YEAR_RE.match(first) and (
                    len(cells) == 1 or _SECTION_RE.match(first)):
                title = first
                i += 1
                continue

        # A header is one or two adjacent text-only rows sitting right on
        # top of a row that carries numbers — or, for text-only tables
        # (Registration schedule), the first wide row of the sheet.
        if _is_header_like(cells):
            nxt = grid[i + 1] if i + 1 < len(grid) else []
            numbers_follow = any(_is_value_num(v) for _, v in next_nonempty(i))
            first_text_table = not headers and _is_header_like(cells, short=True)
            two_row = _is_header_like(nxt) and (
                any(_is_value_num(v) for _, v in next_nonempty(i + 1))
                or (first_text_table and _is_header_like(nxt, short=True)))
            if two_row or numbers_follow or first_text_table:
                header_rows = [cells, nxt] if two_row else [cells]
                headers = _build_headers(header_rows)
                stack = []
                started = True
                lines.append("Kolom: " + " | ".join(_fmt(v) for _, v in cells))
                i += 2 if two_row else 1
                continue
        started = True

        # Label cells = text before the first number; the rest are values.
        first_num = next((c for c, v in cells if _is_value_num(v)), None)
        if first_num is None:
            label_cells, value_cells = cells[:1], cells[1:]
        else:
            label_cells = [(c, v) for c, v in cells if c < first_num and isinstance(v, str)]
            value_cells = [(c, v) for c, v in cells if c >= first_num or not isinstance(v, str)]
            value_cells = [(c, v) for c, v in value_cells if (c, v) not in label_cells]

        if not label_cells:
            stack = []  # e.g. "1 | Machinery | …" — a new numbered group, not a child row
        percent_row = False
        for c, v in label_cells:
            if v in ("%", "ratio") and stack:
                percent_row = True
                continue
            while stack and stack[-1][0] >= c:
                stack.pop()
            stack.append((c, v))
        path = [lbl for _, lbl in stack][-_MAX_PATH_DEPTH:]
        if percent_row:
            path = path + ["%"]

        occupied = {c for c, _ in cells}
        parts = []
        for c, v in value_cells:
            hdr = headers.get(c)
            if hdr is None:
                # Sub-rows are often indented by shifting the whole row a
                # column or two right (merged cells) — borrow the header of
                # the nearest free column to the left.
                for back in (1, 2):
                    if c - back in headers and c - back not in occupied:
                        hdr = headers[c - back]
                        break
            if hdr is None and _is_num(v) and headers:
                continue  # helper column outside the table's header span
            pct = percent_row or bool(hdr and any(h in hdr.lower() for h in _PERCENT_HINTS))
            parts.append(f"{hdr}: {_fmt(v, pct)}" if hdr else _fmt(v, pct))

        label = " > ".join(path) if path else ""
        if not label and not parts:
            i += 1
            continue
        body = f"{label} — {' · '.join(parts)}" if parts and label else (label or " · ".join(parts))
        tag = f"[{source_for_year(year)} · {sheet}" + (f" · {unit}" if unit else "") + "]"
        lines.append(f"{tag} {body}")
        i += 1

    return title or sheet, lines


def body_sheets(wb) -> list[str]:
    """Visible sheets before the 'Appendix→' divider (all visible sheets
    when the workbook has no divider)."""
    out = []
    for meta in wb.sheets_metadata:
        if meta.name.startswith(APPENDIX_PREFIX):
            break
        if str(meta.visible).lower().endswith("visible") and "hidden" not in str(meta.visible).lower():
            out.append(meta.name)
    return out


def workbook_documents(path: str, year: int) -> list[dict]:
    """One {sheet, title, text} per body sheet, ready for rag_service.ingest_text."""
    from python_calamine import CalamineWorkbook  # only the import script needs it
    wb = CalamineWorkbook.from_path(path)
    docs, seen = [], set()
    for sheet in body_sheets(wb):
        rows = wb.get_sheet_by_name(sheet).to_python(skip_empty_area=False)
        sheet_title, lines = _sheet_lines(rows, year, sheet)
        if not lines:
            continue
        title = f"{sheet_title}"
        if title in seen:
            title = f"{sheet_title} ({sheet})"
        seen.add(title)
        intro = (
            f"Business Plan {year} PT CKD OTTO Pharmaceuticals — {sheet_title} (sheet '{sheet}'). "
            f"Kolom bertanda (P) adalah angka rencana (Plan) tahun {year}; kolom tahun sebelumnya "
            f"adalah angka pembanding dari dokumen yang sama."
        )
        docs.append({"sheet": sheet, "title": title, "text": "\n\n".join([intro] + lines)})
    return docs
