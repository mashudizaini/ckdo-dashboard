"""
Exchange Rate Service — Bank Indonesia Kurs Transaksi
Scrapes https://www.bi.go.id/id/statistik/informasi-kurs/transaksi-bi/Default.aspx
using stdlib urllib.request + lxml (no httpx/requests/aiohttp required).

Cache: module-level in-memory, 4-hour TTL.
"""
import re
import ssl
import time
import urllib.request
from datetime import datetime, timezone

from lxml import html as lhtml

BI_URL = "https://www.bi.go.id/id/statistik/informasi-kurs/transaksi-bi/Default.aspx"
_TTL = 4 * 3600  # 4 hours

_CACHE: dict = {"rates": [], "date": None, "cached_at": 0.0, "error": None}

CURRENCY_FLAGS = {
    "AED": "🇦🇪", "AUD": "🇦🇺", "BND": "🇧🇳", "CAD": "🇨🇦",
    "CHF": "🇨🇭", "CNH": "🇨🇳", "CNY": "🇨🇳", "DKK": "🇩🇰",
    "EUR": "🇪🇺", "GBP": "🇬🇧", "HKD": "🇭🇰", "JPY": "🇯🇵",
    "KRW": "🇰🇷", "KWD": "🇰🇼", "LAK": "🇱🇦", "MYR": "🇲🇾",
    "NOK": "🇳🇴", "NZD": "🇳🇿", "PGK": "🇵🇬", "PHP": "🇵🇭",
    "SAR": "🇸🇦", "SEK": "🇸🇪", "SGD": "🇸🇬", "THB": "🇹🇭",
    "USD": "🇺🇸", "VND": "🇻🇳",
}

CURRENCY_NAMES = {
    "AED": "UAE Dirham",            "AUD": "Australian Dollar",
    "BND": "Brunei Dollar",         "CAD": "Canadian Dollar",
    "CHF": "Swiss Franc",           "CNH": "Chinese Yuan (Offshore)",
    "CNY": "Chinese Yuan Renminbi", "DKK": "Danish Krone",
    "EUR": "Euro",                  "GBP": "British Pound Sterling",
    "HKD": "Hong Kong Dollar",      "JPY": "Japanese Yen",
    "KRW": "South Korean Won",      "KWD": "Kuwaiti Dinar",
    "LAK": "Lao Kip",               "MYR": "Malaysian Ringgit",
    "NOK": "Norwegian Krone",       "NZD": "New Zealand Dollar",
    "PGK": "Papua New Guinea Kina", "PHP": "Philippine Peso",
    "SAR": "Saudi Riyal",           "SEK": "Swedish Krona",
    "SGD": "Singapore Dollar",      "THB": "Thai Baht",
    "USD": "US Dollar",             "VND": "Vietnamese Dong",
}

# Common browser headers — same as Chrome on Windows
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
}


def _parse_idr(s: str) -> float | None:
    """Convert Indonesian number format '4.923,49' → 4923.49."""
    try:
        return float(s.strip().replace(".", "").replace(",", "."))
    except (ValueError, AttributeError):
        return None


def _fetch_url(url: str, timeout: int = 20) -> bytes:
    """
    Fetch URL with up to 3 attempts using progressively more permissive SSL settings.
    Raises RuntimeError with a descriptive message if all attempts fail.
    """
    req = urllib.request.Request(url, headers=_HEADERS)
    errors = []

    # Attempt 1 — default SSL (system cert store)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception as e1:
        errors.append(f"default-ssl: {type(e1).__name__}({e1})")

    # Attempt 2 — SSL without hostname check
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.read()
    except Exception as e2:
        errors.append(f"no-hostname: {type(e2).__name__}({e2})")

    # Attempt 3 — SSL fully disabled
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.read()
    except Exception as e3:
        errors.append(f"no-verify: {type(e3).__name__}({e3})")

    raise RuntimeError(
        f"Tidak bisa mengakses bi.go.id setelah 3 percobaan: {' | '.join(errors)}"
    )


def _scrape() -> dict:
    """Fetch BI Kurs Transaksi page and parse rate table. Raises on any failure."""
    raw = _fetch_url(BI_URL, timeout=25)

    if len(raw) < 5_000:
        raise RuntimeError(
            f"Respons bi.go.id terlalu kecil ({len(raw)} bytes) — "
            "kemungkinan bot-detection atau redirect halaman."
        )

    tree = lhtml.fromstring(raw)

    # The exchange-rate data table has class "table-lg" (only one on the page)
    tables = tree.xpath('//table[contains(@class,"table-lg")]')
    if not tables:
        # Try to find any table that looks like currency data (fallback)
        tables = tree.xpath(
            '//table[.//td[normalize-space(text())="USD"] or .//td[normalize-space(text())="EUR"]]'
        )

    if not tables:
        raise RuntimeError(
            f"Tabel kurs tidak ditemukan di halaman BI (html_size={len(raw)})."
        )

    tbl   = tables[0]
    rows  = tbl.xpath(".//tbody/tr")
    if not rows:
        raise RuntimeError("Tabel kurs ditemukan tetapi tidak ada baris data.")

    rates = []
    for row in rows:
        cells = [td.text_content().strip() for td in row.xpath(".//td")]
        if len(cells) < 4:
            continue
        code         = cells[0].strip()
        denomination = _parse_idr(cells[1]) or 1
        sell         = _parse_idr(cells[2])
        buy          = _parse_idr(cells[3])
        # Skip rows where code looks wrong (too long or has no letters)
        if not code or len(code) > 5 or not code[0].isalpha():
            continue
        rates.append({
            "code":         code,
            "name":         CURRENCY_NAMES.get(code, code),
            "flag":         CURRENCY_FLAGS.get(code, ""),
            "denomination": int(denomination),
            "sell":         sell,
            "buy":          buy,
        })

    if not rates:
        sample = [td.text_content().strip() for td in rows[0].xpath(".//td")][:6]
        raise RuntimeError(
            f"Tabel kurs ada {len(rows)} baris tetapi tidak ada data yang valid. "
            f"Sample row: {sample}"
        )

    # Extract date — looks for "03 Jul 2026" or "3 Juli 2026"
    page_text  = tree.text_content()
    date_match = re.search(r"\b\d{1,2}\s+\w{2,8}\s+\d{4}\b", page_text)
    date_str   = date_match.group(0) if date_match else None

    return {"rates": rates, "date": date_str}


def get_rates(force_refresh: bool = False) -> dict:
    """
    Return cached exchange rates. Auto-refreshes when cache is older than 4 hours.
    If scraping fails, returns last cached rates (may be []) with an error message.
    """
    now      = time.time()
    is_fresh = bool(_CACHE["cached_at"]) and (now - _CACHE["cached_at"]) < _TTL

    if not force_refresh and is_fresh and _CACHE["rates"]:
        return {
            "rates":      _CACHE["rates"],
            "date":       _CACHE["date"],
            "cached_at":  _iso(now),
            "from_cache": True,
            "error":      None,
            "source":     "Bank Indonesia — Kurs Transaksi BI",
        }

    try:
        result           = _scrape()
        _CACHE["rates"]     = result["rates"]
        _CACHE["date"]      = result["date"]
        _CACHE["cached_at"] = now
        _CACHE["error"]     = None
    except Exception as exc:
        _CACHE["error"] = str(exc)

    return {
        "rates":      _CACHE["rates"],
        "date":       _CACHE["date"],
        "cached_at":  _iso(_CACHE["cached_at"]) if _CACHE["cached_at"] else None,
        "from_cache": False,
        "error":      _CACHE["error"],
        "source":     "Bank Indonesia — Kurs Transaksi BI",
    }


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
