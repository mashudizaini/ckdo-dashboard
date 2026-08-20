"""
Exchange Rate Service — Multi-source: Bank Indonesia + alternatives
Sources:
  1. bi_html           — scrape bi.go.id (existing implementation)
  2. exchangerate_api  — open.er-api.com (free, no key, daily)
  3. frankfurter       — api.frankfurter.dev (free, no key, daily)
Cache: module-level in-memory, 4-hour TTL, keyed by source + as_of_date.
"""
import http.cookiejar
import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from html.parser import HTMLParser

BI_URL = "https://www.bi.go.id/id/statistik/informasi-kurs/transaksi-bi/Default.aspx"
_TTL = 4 * 3600

_CACHE: dict = {}

AVAILABLE_SOURCES = [
    {"id": "auto",              "name": "Auto (BI -> ExchangeRate-API -> Frankfurter)", "needs_key": False},
    {"id": "bi_html",           "name": "Bank Indonesia - Kurs Transaksi BI",          "needs_key": False},
    {"id": "exchangerate_api",  "name": "ExchangeRate-API (mid-market)",               "needs_key": False},
    {"id": "frankfurter",       "name": "Frankfurter / ECB (mid-market)",              "needs_key": False},
]

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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _parse_idr(s: str) -> float | None:
    try:
        return float(s.strip().replace(".", "").replace(",", "."))
    except (ValueError, AttributeError):
        return None


def _mid_rate(sell, buy):
    if sell and buy:
        return (sell + buy) / 2
    return sell or buy


# ── HTML Parser (BI scrape) ───────────────────────────────────────────────────

class _RateParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._in_target = False
        self._depth = 0
        self._in_tbody = False
        self._in_tr = False
        self._in_td = False
        self._cell_buf = []
        self._row_buf = []
        self.rows: list[list[str]] = []
        self.all_text: list[str] = []

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
            self._in_tr = True
            self._row_buf = []
        elif tag == "td" and self._in_tr:
            self._in_td = True
            self._cell_buf = []

    def handle_endtag(self, tag):
        if tag == "table" and self._in_target:
            self._depth -= 1
            if self._depth == 0:
                self._in_target = False
                self._in_tbody = False
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


# ── Source 1: BI HTML scrape ──────────────────────────────────────────────────

def _fetch_bi_html(timeout: int = 25) -> dict:
    req = urllib.request.Request(BI_URL, headers=_HEADERS)
    errors = []

    for label, ctx in [
        ("default", None),
        ("no-hostname", _make_ssl_ctx()),
        ("no-verify", _make_ssl_ctx(verify=False)),
    ]:
        try:
            kw = {"timeout": timeout}
            if ctx is not None:
                kw["context"] = ctx
            with urllib.request.urlopen(req, **kw) as r:
                raw = r.read()
                enc = r.headers.get_content_charset("utf-8")
                html = raw.decode(enc, errors="replace")
            break
        except Exception as e:
            errors.append(f"{label}: {type(e).__name__}({e})")
    else:
        raise RuntimeError(
            f"Tidak bisa mengakses bi.go.id setelah 3 percobaan — {' | '.join(errors)}"
        )

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
        code = row[0].strip()
        denomination = _parse_idr(row[1]) or 1
        sell = _parse_idr(row[2])
        buy = _parse_idr(row[3])
        if not code or len(code) > 5 or not code[0].isalpha():
            continue
        rates.append({
            "code": code,
            "name": CURRENCY_NAMES.get(code, code),
            "denomination": int(denomination),
            "sell": sell,
            "buy": buy,
        })

    if not rates:
        sample = parser.rows[:2] if parser.rows else []
        raise RuntimeError(
            f"Tabel ada {len(parser.rows)} baris tapi tidak bisa di-parse. Sample: {sample}"
        )

    full_text = "".join(parser.all_text)
    date_match = re.search(r"\b\d{1,2}\s+\w{2,8}\s+\d{4}\b", full_text)
    date_str = date_match.group(0).strip() if date_match else None

    return {"rates": rates, "date": date_str, "source": "bi_html"}


def _make_ssl_ctx(verify: bool = True):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    if not verify:
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


# ── Source 1b: BI HTML scrape — historical date via the "Harian" search ───────
#
# bi.go.id's rate page is a legacy ASP.NET/SharePoint WebForms page — the
# "Harian" date search is a form postback, not a URL parameter. Replaying it
# from the server requires, in order:
#   1. A GET to pick up session cookies + __VIEWSTATE/__EVENTVALIDATION
#      (the postback is rejected without a matching viewstate from the same
#      session).
#   2. A POST of every hidden field from that GET, plus txtTanggal (the date
#      — the field's own placeholder says "dd-mm-yyyy" but the server
#      actually parses it as MM-DD-YYYY, confirmed by probing), the search
#      button's name=value pair, and hidSourceID set to that button's client
#      ID — its onclick JS (SetSource) sets this before the real browser
#      submits, and the search silently no-ops (returns today's default
#      table) without it.
# Confirmed against the live site: searching a past date returns a distinct
# gvSearchResult1 table (no <tbody>, unlike the default live table) labelled
# with the requested date.

def _bi_opener():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def _bi_urlopen(opener, req, timeout: int) -> str:
    errors = []
    for label, ctx in [
        ("default", None),
        ("no-hostname", _make_ssl_ctx()),
        ("no-verify", _make_ssl_ctx(verify=False)),
    ]:
        try:
            kw = {"timeout": timeout}
            if ctx is not None:
                kw["context"] = ctx
            with opener.open(req, **kw) as r:
                raw = r.read()
                enc = r.headers.get_content_charset("utf-8")
                return raw.decode(enc, errors="replace")
        except Exception as e:
            errors.append(f"{label}: {type(e).__name__}({e})")
    raise RuntimeError(f"Tidak bisa mengakses bi.go.id setelah 3 percobaan — {' | '.join(errors)}")


def _extract_hidden_fields(html: str) -> dict:
    fields = {}
    for m in re.finditer(r'<input[^>]*type="hidden"[^>]*/?>', html, re.IGNORECASE):
        tag = m.group(0)
        nm = re.search(r'name="([^"]*)"', tag)
        if not nm:
            continue
        val = re.search(r'value="([^"]*)"', tag)
        fields[nm.group(1)] = val.group(1) if val else ""
    return fields


def _parse_search_result_table(html: str) -> list[dict]:
    m = re.search(r'<table[^>]*id="[^"]*_gvSearchResult1"[^>]*>(.*?)</table>', html, re.IGNORECASE | re.DOTALL)
    if not m:
        return []
    rates = []
    for row_m in re.finditer(r'<tr[^>]*>(.*?)</tr>', m.group(1), re.IGNORECASE | re.DOTALL):
        cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row_m.group(1), re.IGNORECASE | re.DOTALL)
        cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        if len(cells) < 4:
            continue
        code = cells[0].strip()
        if not code or len(code) > 5 or not code[0].isalpha():
            continue
        # Unlike the live table's "Nilai" column (plain "1"), this GridView
        # renders it in plain decimal notation ("1.00", "100.00") rather
        # than Indonesian thousands-grouping — _parse_idr would misread
        # "100.00" as 10000.
        try:
            denomination = float(cells[1].strip())
        except (ValueError, AttributeError):
            denomination = None
        rates.append({
            "code": code,
            "name": CURRENCY_NAMES.get(code, code),
            "denomination": int(denomination or 1),
            "sell": _parse_idr(cells[2]),
            "buy": _parse_idr(cells[3]),
        })
    return rates


def _fetch_bi_html_for_date(date_iso: str, timeout: int = 25) -> dict:
    opener = _bi_opener()
    html = _bi_urlopen(opener, urllib.request.Request(BI_URL, headers=_HEADERS), timeout)

    if len(html) < 5_000:
        raise RuntimeError(f"Respons bi.go.id terlalu kecil ({len(html)} chars) saat mengambil form pencarian.")

    m = re.search(r'name="([^"]*\$txtTanggal)"', html)
    if not m:
        raise RuntimeError(
            "Field pencarian tanggal (txtTanggal) tidak ditemukan di halaman BI — "
            "kemungkinan struktur halaman bi.go.id berubah."
        )
    prefix = m.group(1)[: -len("txtTanggal")]
    txt_name = prefix + "txtTanggal"
    btn_name = prefix + "btnSearch2"
    hid_name = prefix + "hidSourceID"

    y, mo, d = date_iso.split("-")
    fields = _extract_hidden_fields(html)
    fields[txt_name] = f"{mo}-{d}-{y}"
    fields[btn_name] = "Cari"
    fields[hid_name] = btn_name.replace("$", "_")

    post_req = urllib.request.Request(
        BI_URL,
        data=urllib.parse.urlencode(fields).encode("utf-8"),
        headers={**_HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
    )
    result_html = _bi_urlopen(opener, post_req, timeout)

    rates = _parse_search_result_table(result_html)
    if not rates:
        raise RuntimeError(
            f"Tidak ada data Kurs Transaksi BI untuk tanggal {date_iso} "
            "(kemungkinan hari libur/bukan hari kerja, atau tanggal belum tersedia di bi.go.id)."
        )

    label_m = re.search(r'id="[^"]*_lblKursTransaksiKTBI2"[^>]*>([^<]*)<', result_html)
    date_str = label_m.group(1).strip() if label_m else date_iso

    return {"rates": rates, "date": date_str, "source": "bi_html"}


# ── Source 2: ExchangeRate-API (open access) ──────────────────────────────────

def _fetch_exchangerate_api(timeout: int = 20) -> dict:
    url = "https://open.er-api.com/v6/latest/IDR"
    req = urllib.request.Request(url, headers={"User-Agent": _HEADERS["User-Agent"]})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            data = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise RuntimeError(f"ExchangeRate-API error: {e}")

    if data.get("result") != "success":
        raise RuntimeError(f"ExchangeRate-API returned non-success: {data.get('result')}")

    rates = []
    base_rates = data.get("rates", {})
    ts = data.get("time_last_update_utc", "")
    date_str = None
    if ts:
        try:
            date_str = datetime.strptime(ts, "%a, %d %b %Y %H:%M:%S %z").strftime("%d %b %Y")
        except Exception:
            date_str = ts

    for code, name in CURRENCY_NAMES.items():
        if code == "IDR":
            continue
        inv = base_rates.get(code)
        if inv is None or inv <= 0:
            continue
        mid = round(1.0 / inv, 4)
        rates.append({
            "code": code,
            "name": name,
            "denomination": 1,
            "sell": mid,
            "buy": mid,
        })

    if not rates:
        raise RuntimeError("ExchangeRate-API mengembalikan data kosong.")

    return {"rates": rates, "date": date_str, "source": "exchangerate_api"}


# ── Source 3: Frankfurter / ECB ───────────────────────────────────────────────

def _fetch_frankfurter(timeout: int = 20) -> dict:
    url = "https://api.frankfurter.dev/v1/latest?from=IDR"
    req = urllib.request.Request(url, headers={"User-Agent": _HEADERS["User-Agent"]})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            data = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise RuntimeError(f"Frankfurter error: {e}")

    rates = []
    base_rates = data.get("rates", {})
    date_str = data.get("date", "")

    for code, name in CURRENCY_NAMES.items():
        if code == "IDR":
            continue
        inv = base_rates.get(code)
        if inv is None or inv <= 0:
            continue
        mid = round(1.0 / inv, 4)
        rates.append({
            "code": code,
            "name": name,
            "denomination": 1,
            "sell": mid,
            "buy": mid,
        })

    if not rates:
        raise RuntimeError("Frankfurter mengembalikan data kosong.")

    date_str_fmt = None
    if date_str:
        try:
            date_str_fmt = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d %b %Y")
        except Exception:
            date_str_fmt = date_str

    return {"rates": rates, "date": date_str_fmt, "source": "frankfurter"}


# ── Dispatcher ────────────────────────────────────────────────────────────────

_FETCHERS = {
    "bi_html":          _fetch_bi_html,
    "exchangerate_api": _fetch_exchangerate_api,
    "frankfurter":      _fetch_frankfurter,
}

_SOURCE_LABELS = {
    "bi_html":          "Bank Indonesia - Kurs Transaksi BI",
    "exchangerate_api": "ExchangeRate-API (mid-market)",
    "frankfurter":      "Frankfurter / ECB (mid-market)",
}


def _cache_key(source: str, as_of_date: str | None = None) -> str:
    return f"rates:{source}:{as_of_date or 'latest'}"


def get_rates(source: str = "auto", force_refresh: bool = False, as_of_date: str | None = None) -> dict:
    now = time.time()

    # A past date can only be answered by replaying BI's own historical
    # "Harian" search (see _fetch_bi_html_for_date) — the other sources have
    # no historical endpoint, so silently substituting them would return a
    # rate that isn't actually as of the requested date. as_of_date == today
    # falls through to the normal fast live-scrape path below.
    historical = bool(as_of_date) and as_of_date != date.today().isoformat()

    if historical:
        candidates = ["bi_html"]
    elif source == "auto":
        candidates = ["bi_html", "exchangerate_api", "frankfurter"]
    elif source in _FETCHERS:
        candidates = [source]
    else:
        candidates = ["bi_html", "exchangerate_api", "frankfurter"]

    last_error = None
    used_source = None
    result = None

    for src in candidates:
        ck = _cache_key(src, as_of_date if historical else None)
        cached = _CACHE.get(ck, {})
        is_fresh = bool(cached.get("cached_at")) and (now - cached["cached_at"]) < _TTL

        if not force_refresh and is_fresh and cached.get("rates"):
            result = cached
            used_source = src
            break

        try:
            fetched = _fetch_bi_html_for_date(as_of_date) if (historical and src == "bi_html") else _FETCHERS[src]()
            result = fetched
            _CACHE[ck] = {
                "rates": fetched["rates"],
                "date": fetched["date"],
                "cached_at": now,
                "error": None,
                "source": src,
            }
            used_source = src
            break
        except Exception as exc:
            last_error = str(exc)
            _CACHE[ck] = {
                "rates": [],
                "date": None,
                "cached_at": now,
                "error": str(exc),
                "source": src,
            }
            continue

    if result is None:
        result = {"rates": [], "date": None, "error": last_error or "Tidak ada sumber kurs yang berhasil."}

    return {
        "rates":          result.get("rates", []),
        "date":           result.get("date"),
        "cached_at":      _iso(result["cached_at"]) if result.get("cached_at") else None,
        "from_cache":     bool(result.get("rates")) and not force_refresh and result.get("cached_at") and (now - result["cached_at"]) < _TTL,
        "error":          result.get("error"),
        "source":         _SOURCE_LABELS.get(used_source, used_source or "unknown"),
        "source_id":      used_source or "unknown",
        "available_sources": AVAILABLE_SOURCES,
    }


# ── Oracle EBS GL Daily Rates push ───────────────────────────────────────────

def push_rates_to_ebs(
    rates: list[dict],
    rate_date: str,
    rate_type: str,
    rate_source: str,
    currencies: list[str],
) -> list[dict]:
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
    results = []

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
            else:
                s, b = r.get("sell"), r.get("buy")
                value = _mid_rate(s, b)

            if value is None:
                results.append({"code": code, "status": "skipped", "reason": "Nilai kurs kosong"})
                continue

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
                        "code": code,
                        "status": "error",
                        "action": "failed",
                        "rate": value,
                        "error": str(e_update),
                        "insert_error": str(e_insert),
                    })
        cursor.close()

    return results
