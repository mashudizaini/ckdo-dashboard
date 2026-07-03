"""
Exchange Rate Service — Bank Indonesia Kurs Transaksi
Uses httpx (already in requirements.txt) + stdlib html.parser — zero extra deps.
Cache: module-level in-memory, 4-hour TTL.
"""
import re
import ssl
import time
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

BI_URL = "https://www.bi.go.id/id/statistik/informasi-kurs/transaksi-bi/Default.aspx"
_TTL   = 4 * 3600  # 4 hours

_CACHE: dict = {"rates": [], "date": None, "cached_at": 0.0, "error": None}

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

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
}


# ── HTML Parser (stdlib, no lxml needed) ─────────────────────────────────────

class _RateParser(HTMLParser):
    """
    Extract rows from the BI rate table (class contains "table-lg").
    Also collects all text to find the published date.
    """
    def __init__(self):
        super().__init__()
        self._in_target = False   # inside <table class="...table-lg...">
        self._depth     = 0       # table nesting depth
        self._in_tbody  = False
        self._in_tr     = False
        self._in_td     = False
        self._cell_buf  = []
        self._row_buf   = []
        self.rows: list[list[str]] = []
        self.all_text: list[str]   = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "table":
            if not self._in_target and "table-lg" in d.get("class", ""):
                self._in_target = True
                self._depth = 1
            elif self._in_target:
                self._depth += 1
        elif tag == "tbody" and self._in_target and self._depth == 1:
            self._in_tbody = True
        elif tag == "tr" and self._in_tbody:
            self._in_tr   = True
            self._row_buf = []
        elif tag == "td" and self._in_tr:
            self._in_td   = True
            self._cell_buf = []

    def handle_endtag(self, tag):
        if tag == "table" and self._in_target:
            self._depth -= 1
            if self._depth == 0:
                self._in_target = False
                self._in_tbody  = False
        elif tag == "tbody":
            self._in_tbody = False
        elif tag == "tr" and self._in_tr:
            self._in_tr = False
            if self._row_buf:
                self.rows.append(self._row_buf[:])
        elif tag == "td" and self._in_td:
            self._in_td = False
            self._row_buf.append("".join(self._cell_buf).strip())
            self._cell_buf = []

    def handle_data(self, data):
        if self._in_td:
            self._cell_buf.append(data)
        self.all_text.append(data)


# ── Core functions ────────────────────────────────────────────────────────────

def _parse_idr(s: str) -> float | None:
    """'4.923,49' → 4923.49  (Indonesian thousand/decimal separator)."""
    try:
        return float(s.strip().replace(".", "").replace(",", "."))
    except (ValueError, AttributeError):
        return None


def _fetch_html(timeout: int = 25) -> str:
    """
    Fetch the BI page using urllib (stdlib).
    Three attempts with progressively more permissive SSL settings.
    """
    req    = urllib.request.Request(BI_URL, headers=_HEADERS)
    errors = []

    # Attempt 1 — system SSL cert store (default)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            enc = r.headers.get_content_charset("utf-8")
            return raw.decode(enc, errors="replace")
    except Exception as e:
        errors.append(f"ssl-default: {type(e).__name__}({e})")

    # Attempt 2 — skip hostname check
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            raw = r.read()
            enc = r.headers.get_content_charset("utf-8")
            return raw.decode(enc, errors="replace")
    except Exception as e:
        errors.append(f"no-hostname: {type(e).__name__}({e})")

    # Attempt 3 — disable SSL verification entirely
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode    = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            raw = r.read()
            enc = r.headers.get_content_charset("utf-8")
            return raw.decode(enc, errors="replace")
    except Exception as e:
        errors.append(f"no-verify: {type(e).__name__}({e})")

    raise RuntimeError(
        f"Tidak bisa mengakses bi.go.id setelah 3 percobaan — {' | '.join(errors)}"
    )


def _scrape() -> dict:
    html = _fetch_html()

    if len(html) < 5_000:
        raise RuntimeError(
            f"Respons bi.go.id terlalu kecil ({len(html)} chars) — "
            "kemungkinan bot-detection atau halaman error."
        )

    parser = _RateParser()
    parser.feed(html)

    if not parser.rows:
        raise RuntimeError(
            "Tabel kurs (class=table-lg) tidak ditemukan atau kosong di halaman BI."
        )

    rates = []
    for row in parser.rows:
        if len(row) < 4:
            continue
        code         = row[0].strip()
        denomination = _parse_idr(row[1]) or 1
        sell         = _parse_idr(row[2])
        buy          = _parse_idr(row[3])
        if not code or len(code) > 5 or not code[0].isalpha():
            continue
        rates.append({
            "code":         code,
            "name":         CURRENCY_NAMES.get(code, code),
            "denomination": int(denomination),
            "sell":         sell,
            "buy":          buy,
        })

    if not rates:
        sample = parser.rows[:2] if parser.rows else []
        raise RuntimeError(
            f"Tabel ada {len(parser.rows)} baris tapi tidak bisa di-parse. "
            f"Sample: {sample}"
        )

    # Date — e.g. "03 Jul 2026" or "3 Juli 2026"
    full_text  = "".join(parser.all_text)
    date_match = re.search(r"\b\d{1,2}\s+\w{2,8}\s+\d{4}\b", full_text)
    date_str   = date_match.group(0).strip() if date_match else None

    return {"rates": rates, "date": date_str}


def get_rates(force_refresh: bool = False) -> dict:
    """Return cached rates; refresh when cache > 4 h old or force_refresh=True."""
    now      = time.time()
    is_fresh = bool(_CACHE["cached_at"]) and (now - _CACHE["cached_at"]) < _TTL

    if not force_refresh and is_fresh and _CACHE["rates"]:
        return {
            "rates":      _CACHE["rates"],
            "date":       _CACHE["date"],
            "cached_at":  _iso(_CACHE["cached_at"]),
            "from_cache": True,
            "error":      None,
            "source":     "Bank Indonesia — Kurs Transaksi BI",
        }

    try:
        result              = _scrape()
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


# ── Oracle EBS GL Daily Rates push ───────────────────────────────────────────

def push_rates_to_ebs(
    rates: list[dict],
    rate_date: str,     # "2026-07-03"
    rate_type: str,     # "Corporate" | "Spot"
    rate_source: str,   # "jual" | "beli" | "tengah"
    currencies: list[str],
) -> list[dict]:
    """
    Push selected currencies to Oracle EBS using GL_DAILY_RATES_API.
    Tries INSERT first; falls back to UPDATE if the rate already exists.
    Returns list of per-currency results.
    """
    from app.database import get_oracle_connection

    INSERT_SQL = """
    BEGIN
        APPS.GL_DAILY_RATES_API.INSERT_RATE(
            x_from_currency => :from_currency,
            x_to_currency   => 'IDR',
            x_from_date     => TO_DATE(:rate_date, 'YYYY-MM-DD'),
            x_to_date       => TO_DATE(:rate_date, 'YYYY-MM-DD'),
            x_rate          => :rate,
            x_rate_type     => :rate_type,
            x_mode          => 'ORACLE'
        );
    END;
    """
    UPDATE_SQL = """
    BEGIN
        APPS.GL_DAILY_RATES_API.UPDATE_RATE(
            x_from_currency => :from_currency,
            x_to_currency   => 'IDR',
            x_from_date     => TO_DATE(:rate_date, 'YYYY-MM-DD'),
            x_to_date       => TO_DATE(:rate_date, 'YYYY-MM-DD'),
            x_rate          => :rate,
            x_rate_type     => :rate_type,
            x_mode          => 'ORACLE'
        );
    END;
    """

    rate_map = {r["code"]: r for r in rates}
    results  = []

    with get_oracle_connection() as conn:
        cursor = conn.cursor()
        for code in currencies:
            r = rate_map.get(code)
            if not r:
                results.append({"code": code, "status": "skipped", "reason": "Kurs tidak tersedia"})
                continue

            if rate_source == "jual":
                value = r.get("sell")
            elif rate_source == "beli":
                value = r.get("buy")
            else:  # tengah (midpoint)
                s, b  = r.get("sell"), r.get("buy")
                value = ((s or 0) + (b or 0)) / 2 if (s and b) else (s or b)

            if value is None:
                results.append({"code": code, "status": "skipped", "reason": "Nilai kurs kosong"})
                continue

            # Normalise: JPY per-100 → per-1
            denom = r.get("denomination", 1)
            if denom and denom > 1:
                value = round(value / denom, 6)

            params = {"from_currency": code, "rate_date": rate_date,
                      "rate": value, "rate_type": rate_type}
            try:
                cursor.execute(INSERT_SQL, params)
                conn.commit()
                results.append({"code": code, "status": "success", "action": "inserted", "rate": value})
            except Exception as e_insert:
                try:
                    conn.rollback()
                    cursor.execute(UPDATE_SQL, params)
                    conn.commit()
                    results.append({"code": code, "status": "success", "action": "updated", "rate": value})
                except Exception as e_update:
                    conn.rollback()
                    results.append({
                        "code":   code,
                        "status": "error",
                        "action": "failed",
                        "rate":   value,
                        "error":  str(e_update),
                        "insert_error": str(e_insert),
                    })
        cursor.close()

    return results


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
