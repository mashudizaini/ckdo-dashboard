"""
Exchange Rate Service — Bank Indonesia Kurs Transaksi
Scrapes https://www.bi.go.id/id/statistik/informasi-kurs/transaksi-bi/Default.aspx
using only stdlib urllib.request + lxml (no httpx/requests/aiohttp required).

Cache: module-level in-memory, 4-hour TTL (BI publishes rates once per business day).
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


def _parse_idr(s: str) -> float | None:
    """Convert Indonesian number format '4.923,49' → 4923.49."""
    try:
        return float(s.strip().replace(".", "").replace(",", "."))
    except (ValueError, AttributeError):
        return None


def _fetch_raw(url: str) -> bytes:
    """Fetch URL using urllib with a fallback to no-SSL-verify if cert check fails."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read()
    except Exception:
        # Fall back to no-verify (some environments have cert chain issues with bi.go.id)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
            return r.read()


def _scrape() -> dict:
    """Scrape BI Kurs Transaksi page and return parsed rates + date."""
    raw = _fetch_raw(BI_URL)
    tree = lhtml.fromstring(raw)

    # The rate table has class "table-lg" — one match on the page
    tables = tree.xpath('//table[contains(@class,"table-lg")]')
    if not tables:
        raise RuntimeError("Tabel kurs tidak ditemukan di halaman BI")

    tbl = tables[0]
    rows = tbl.xpath(".//tbody/tr")
    if not rows:
        raise RuntimeError("Tidak ada baris data kurs")

    rates = []
    for row in rows:
        cells = [td.text_content().strip() for td in row.xpath(".//td")]
        if len(cells) < 4:
            continue
        code        = cells[0].strip()
        denomination = _parse_idr(cells[1]) or 1
        sell        = _parse_idr(cells[2])
        buy         = _parse_idr(cells[3])
        if not code or len(code) > 5:
            continue
        rates.append({
            "code":         code,
            "name":         CURRENCY_NAMES.get(code, code),
            "flag":         CURRENCY_FLAGS.get(code, "🏳"),
            "denomination": int(denomination),
            "sell":         sell,
            "buy":          buy,
        })

    # Find date — pattern like "03 Jul 2026"
    page_text = tree.text_content()
    date_matches = re.findall(r"\d{1,2}\s+\w{3,}\s+\d{4}", page_text)
    date_str = date_matches[0] if date_matches else None

    return {"rates": rates, "date": date_str}


def get_rates(force_refresh: bool = False) -> dict:
    """
    Return cached rates (refreshed every 4 hours).
    If scraping fails, returns last cached rates with error flag.
    """
    now = time.time()
    is_fresh = _CACHE["cached_at"] and (now - _CACHE["cached_at"]) < _TTL

    if not force_refresh and is_fresh and _CACHE["rates"]:
        return {
            "rates":      _CACHE["rates"],
            "date":       _CACHE["date"],
            "cached_at":  datetime.fromtimestamp(_CACHE["cached_at"], tz=timezone.utc).isoformat(),
            "from_cache": True,
            "error":      None,
        }

    try:
        result = _scrape()
        _CACHE["rates"]     = result["rates"]
        _CACHE["date"]      = result["date"]
        _CACHE["cached_at"] = now
        _CACHE["error"]     = None
    except Exception as exc:
        _CACHE["error"] = str(exc)

    return {
        "rates":      _CACHE["rates"],
        "date":       _CACHE["date"],
        "cached_at":  (
            datetime.fromtimestamp(_CACHE["cached_at"], tz=timezone.utc).isoformat()
            if _CACHE["cached_at"] else None
        ),
        "from_cache": False,
        "error":      _CACHE["error"],
        "source":     "Bank Indonesia — Kurs Transaksi BI",
    }
