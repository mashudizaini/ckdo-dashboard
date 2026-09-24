"""
The tools the model calls (blueprint section 7): find_marts, run_sql, and
intent tools whose SQL is written and tested here.

Intent tools answer the frequent questions with the highest accuracy; run_sql
is the guarded fallback for ad-hoc ones. Every function takes the resolved
Caller first and checks mart access before touching the database, so a 403
never depends on the model choosing not to try.

Matching rules carried over from eis_tools (and the incidents behind them):
item and invoice codes match exactly, case-insensitively; names match as a
substring; one `item` argument accepts either, because people ask by
substance name as often as by code.
"""
from datetime import date

from app.services.ebs_mart import access, query, sql_guard
from app.services.ebs_mart.access import Caller
from app.services.ebs_mart.constants import MARTS


def _like(v: str | None) -> str | None:
    return f"%{v.strip()}%" if v and v.strip() else None


def _val(v):
    return v.strip() if isinstance(v, str) and v.strip() else (None if isinstance(v, str) else v)


def _run(caller: Caller, mart: str | list[str], sql: str, params: dict, tool: str, args: dict) -> dict:
    marts = [mart] if isinstance(mart, str) else mart
    for m in marts:
        try:
            access.require(caller, m)
        except access.AccessDenied as e:
            query.log_call(caller, tool=tool, marts=marts, args=args, status="DENIED", error=str(e))
            raise
    return query.run(caller, sql, params, tool=tool, marts=marts, args=args)


# ── Discovery ────────────────────────────────────────────────────────────────

def find_marts(caller: Caller, keywords: str) -> dict:
    """Marts relevant to a business phrase, with their full column list.

    Scores each mart by how many words of the phrase hit its synonyms,
    column synonyms, descriptions or domain. Returns whole column lists, not
    only the matching columns: to write a correct SELECT the model needs to
    see amount_remaining_idr next to vendor_name even if only "hutang" matched.
    Marts the caller cannot read are left out entirely — a 403 later is worse
    than never suggesting them."""
    from app.services.ebs_mart.catalog_seed import MART_SYNONYMS

    words = [w for w in (keywords or "").lower().replace(",", " ").split() if len(w) >= 2]
    conn = query._rw()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT mart_name, column_name, data_type, description_id, synonyms, sample_values, domain
                     FROM meta.column_catalog ORDER BY mart_name, column_name"""
            )
            catalog = cur.fetchall()
            cur.execute("SELECT domain, question_id, sql_text FROM meta.golden_query ORDER BY id")
            golden = cur.fetchall()
    finally:
        conn.close()

    by_mart: dict[str, list] = {}
    for row in catalog:
        by_mart.setdefault(row[0], []).append(row)

    scored = []
    for name, rows in by_mart.items():
        if not caller.can_read(name) or not MARTS.get(name, {}).get("built"):
            continue
        meta = MARTS[name]
        haystack = " ".join(
            [name, meta["domain"], meta["description"], meta["grain"], " ".join(MART_SYNONYMS.get(name, []))]
            + [f"{r[1]} {r[3] or ''} {' '.join(r[4] or [])}" for r in rows]
        ).lower()
        score = sum(1 for w in words if w in haystack) if words else 1
        if score:
            scored.append((score, name, rows))
    scored.sort(key=lambda t: -t[0])

    marts_out = []
    for _, name, rows in scored[:4]:
        meta = MARTS[name]
        marts_out.append({
            "mart": f"mart.{name}",
            "domain": meta["domain"],
            "grain": meta["grain"],
            "description": meta["description"],
            "as_of": query.as_of([name]),
            "columns": [
                {"name": r[1], "type": r[2], "description": r[3],
                 **({"synonyms": r[4]} if r[4] else {}),
                 **({"values": r[5]} if r[5] else {})}
                for r in rows
            ],
        })

    picked = {m["mart"] for m in marts_out}
    examples = [
        {"question": q, "sql": s}
        for d, q, s in golden
        if any(p in s for p in picked)
    ][:6]

    not_built = [
        f"mart.{n} (fase {m['phase']})" for n, m in MARTS.items()
        if not m.get("built") and any(w in f"{n} {m['description']} {m['domain']}".lower() for w in words)
    ]

    query.log_call(caller, tool="find_marts", question=keywords, marts=[m["mart"][5:] for m in marts_out],
                   args={"keywords": keywords}, row_count=len(marts_out), status="OK")
    return {
        "marts": marts_out,
        "golden_queries": examples,
        **({"not_available_yet": not_built} if not_built else {}),
        **({"note": "Tidak ada mart yang cocok atau yang boleh Anda akses."} if not marts_out else {}),
    }


def run_sql(caller: Caller, sql: str, question: str = "") -> dict:
    try:
        guarded = sql_guard.validate(sql)
    except sql_guard.SqlRejected as e:
        query.log_call(caller, tool="run_sql", question=question, sql=sql, status="REJECTED", error=str(e))
        raise
    for m in guarded.tables:
        try:
            access.require(caller, m)
        except access.AccessDenied as e:
            query.log_call(caller, tool="run_sql", question=question, sql=sql, marts=guarded.tables,
                           status="DENIED", error=str(e))
            raise
    return query.run(caller, guarded.sql, None, tool="run_sql", marts=guarded.tables, question=question,
                     args={"sql": sql})


def get_data_freshness(caller: Caller) -> dict:
    """Which marts this caller can read, when each was last loaded, and how
    many rows it holds — for "data per kapan?" and for the model to check
    before trusting an empty answer."""
    out = []
    conn = query._reader()
    try:
        with conn.cursor() as cur:
            for name in caller.readable_marts():
                cur.execute(f"SELECT COUNT(*) FROM mart.{name}")
                out.append({"mart": f"mart.{name}", "domain": MARTS[name]["domain"],
                            "row_count": cur.fetchone()[0], "as_of": query.as_of([name])})
        conn.rollback()
    finally:
        conn.close()
    query.log_call(caller, tool="get_data_freshness", row_count=len(out), status="OK")
    return {"marts": out}


# ── AP ───────────────────────────────────────────────────────────────────────

def get_ap_aging(caller: Caller, supplier: str | None = None, min_days_overdue: int | None = None,
                 currency: str | None = None, group_by: str = "supplier") -> dict:
    args = {"supplier": supplier, "min_days_overdue": min_days_overdue, "currency": currency, "group_by": group_by}
    params = {"s": _like(supplier), "d": min_days_overdue, "c": _val(currency)}
    where = """
        WHERE (%(d)s::int  IS NULL OR days_overdue >= %(d)s::int)
          AND (%(s)s::text IS NULL OR vendor_name ILIKE %(s)s::text)
          AND (%(c)s::text IS NULL OR UPPER(currency_code) = UPPER(%(c)s::text))
    """
    if group_by == "bucket":
        sql = f"""
            SELECT aging_bucket, COUNT(*) AS jml_invoice, COUNT(DISTINCT vendor_num) AS jml_supplier,
                   SUM(amount_remaining_idr) AS total_idr
              FROM mart.ap_open_invoice {where}
             GROUP BY aging_bucket, aging_bucket_order ORDER BY aging_bucket_order
        """
    elif group_by == "supplier_bucket":
        sql = f"""
            SELECT vendor_num, vendor_name, aging_bucket, COUNT(*) AS jml_invoice,
                   SUM(amount_remaining_idr) AS total_idr
              FROM mart.ap_open_invoice {where}
             GROUP BY vendor_num, vendor_name, aging_bucket, aging_bucket_order
             ORDER BY vendor_name, aging_bucket_order
        """
    else:
        # The standard aging report shape: one row per supplier, buckets as columns.
        sql = f"""
            SELECT vendor_num, vendor_name,
                   SUM(amount_remaining_idr) FILTER (WHERE aging_bucket = 'Current') AS current_idr,
                   SUM(amount_remaining_idr) FILTER (WHERE aging_bucket = '1-30')    AS d1_30_idr,
                   SUM(amount_remaining_idr) FILTER (WHERE aging_bucket = '31-60')   AS d31_60_idr,
                   SUM(amount_remaining_idr) FILTER (WHERE aging_bucket = '61-90')   AS d61_90_idr,
                   SUM(amount_remaining_idr) FILTER (WHERE aging_bucket = '>90')     AS over_90_idr,
                   SUM(amount_remaining_idr)                                          AS total_idr,
                   COUNT(*)                                                           AS jml_invoice
              FROM mart.ap_open_invoice {where}
             GROUP BY vendor_num, vendor_name
             ORDER BY total_idr DESC
        """
    return _run(caller, "ap_open_invoice", sql, params, "get_ap_aging", args)


def get_ap_open_invoices(caller: Caller, supplier: str | None = None, invoice_num: str | None = None,
                         min_days_overdue: int | None = None, due_from: date | None = None,
                         due_to: date | None = None, currency: str | None = None) -> dict:
    args = {"supplier": supplier, "invoice_num": invoice_num, "min_days_overdue": min_days_overdue,
            "due_from": due_from, "due_to": due_to, "currency": currency}
    sql = """
        SELECT vendor_name, invoice_num, invoice_type, invoice_date, due_date, days_overdue, aging_bucket,
               currency_code, amount_remaining_entered, amount_remaining_idr, payment_num
          FROM mart.ap_open_invoice
         WHERE (%(s)s::text   IS NULL OR vendor_name ILIKE %(s)s::text)
           AND (%(inv)s::text IS NULL OR UPPER(invoice_num) = UPPER(%(inv)s::text))
           AND (%(d)s::int    IS NULL OR days_overdue >= %(d)s::int)
           AND (%(df)s::date  IS NULL OR due_date >= %(df)s::date)
           AND (%(dt)s::date  IS NULL OR due_date <= %(dt)s::date)
           AND (%(c)s::text   IS NULL OR UPPER(currency_code) = UPPER(%(c)s::text))
         ORDER BY due_date, vendor_name, invoice_num
    """
    params = {"s": _like(supplier), "inv": _val(invoice_num), "d": min_days_overdue,
              "df": due_from, "dt": due_to, "c": _val(currency)}
    return _run(caller, "ap_open_invoice", sql, params, "get_ap_open_invoices", args)


def get_ap_payments(caller: Caller, supplier: str | None = None, invoice_num: str | None = None,
                    payment_number: str | None = None, date_from: date | None = None,
                    date_to: date | None = None, group_by: str = "none") -> dict:
    args = {"supplier": supplier, "invoice_num": invoice_num, "payment_number": payment_number,
            "date_from": date_from, "date_to": date_to, "group_by": group_by}
    where = """
         WHERE (%(s)s::text   IS NULL OR vendor_name ILIKE %(s)s::text)
           AND (%(inv)s::text IS NULL OR UPPER(invoice_num) = UPPER(%(inv)s::text))
           AND (%(pn)s::text  IS NULL OR UPPER(payment_number) = UPPER(%(pn)s::text))
           AND (%(df)s::date  IS NULL OR payment_date >= %(df)s::date)
           AND (%(dt)s::date  IS NULL OR payment_date <= %(dt)s::date)
    """
    if group_by == "supplier":
        sql = f"""
            SELECT vendor_name, COUNT(DISTINCT payment_number) AS jml_pembayaran,
                   COUNT(DISTINCT invoice_id) AS jml_invoice, SUM(amount_idr) AS total_idr
              FROM mart.ap_payment_history {where}
             GROUP BY vendor_name ORDER BY total_idr DESC
        """
    elif group_by == "month":
        sql = f"""
            SELECT period_start_date, period_name, COUNT(DISTINCT payment_number) AS jml_pembayaran,
                   SUM(amount_idr) AS total_idr
              FROM mart.ap_payment_history {where}
             GROUP BY period_start_date, period_name ORDER BY period_start_date
        """
    else:
        sql = f"""
            SELECT payment_date, payment_number, payment_method, vendor_name, invoice_num,
                   currency_code, amount_entered, amount_idr, bank_account_name
              FROM mart.ap_payment_history {where}
             ORDER BY payment_date DESC, payment_number
        """
    params = {"s": _like(supplier), "inv": _val(invoice_num), "pn": _val(payment_number),
              "df": date_from, "dt": date_to}
    return _run(caller, "ap_payment_history", sql, params, "get_ap_payments", args)


def get_ap_holds(caller: Caller, supplier: str | None = None, hold_code: str | None = None) -> dict:
    args = {"supplier": supplier, "hold_code": hold_code}
    sql = """
        SELECT vendor_name, invoice_num, invoice_date, hold_code, hold_desc, hold_reason, hold_date,
               days_on_hold, currency_code, invoice_amount_entered, invoice_amount_idr
          FROM mart.ap_invoice_hold
         WHERE (%(s)s::text IS NULL OR vendor_name ILIKE %(s)s::text)
           AND (%(h)s::text IS NULL OR UPPER(hold_code) LIKE UPPER(%(h)s::text) || '%%')
         ORDER BY days_on_hold DESC
    """
    return _run(caller, "ap_invoice_hold", sql, {"s": _like(supplier), "h": _val(hold_code)},
                "get_ap_holds", args)


# ── Inventory ────────────────────────────────────────────────────────────────

_ITEM_FILTER = """(%(item)s::text IS NULL OR UPPER(item_code) = UPPER(%(item)s::text)
                   OR item_desc ILIKE '%%' || %(item)s::text || '%%')"""
_CATEGORY_FILTER = "(%(cat)s::text[] IS NULL OR UPPER(item_category) = ANY(%(cat)s::text[]))"


def _categories(v) -> list[str] | None:
    """item_category arrives as a list from the tool server and as a comma
    string from the admin playground; either way upper-cased exact values
    (API, EXCIPIENT, PRIMER, ...) — a category is a code, not a phrase."""
    if not v:
        return None
    items = v.split(",") if isinstance(v, str) else v
    out = [str(x).strip().upper() for x in items if str(x).strip()]
    return out or None


def get_expiring_lots(caller: Caller, days: int = 90, item: str | None = None,
                      subinventory_type: str | None = "GOOD", include_expired: bool = False,
                      item_category=None) -> dict:
    args = {"days": days, "item": item, "subinventory_type": subinventory_type, "include_expired": include_expired,
            "item_category": item_category}
    sql = f"""
        SELECT item_code, item_desc, item_category, lot_number, expiration_date, days_to_expiry, onhand_qty, uom,
               subinventory_code, subinventory_type, lot_status
          FROM mart.inv_onhand_lot
         WHERE days_to_expiry <= %(days)s::int
           AND (%(incl)s::boolean OR days_to_expiry >= 0)
           AND (%(st)s::text IS NULL OR subinventory_type = UPPER(%(st)s::text))
           AND {_ITEM_FILTER}
           AND {_CATEGORY_FILTER}
         ORDER BY expiration_date, item_code
    """
    params = {"days": days, "incl": include_expired, "st": _val(subinventory_type), "item": _val(item),
              "cat": _categories(item_category)}
    return _run(caller, "inv_onhand_lot", sql, params, "get_expiring_lots", args)


def get_stock_onhand(caller: Caller, item: str | None = None, subinventory: str | None = None,
                     lot_number: str | None = None, subinventory_type: str | None = None,
                     group_by: str = "item", item_category=None) -> dict:
    args = {"item": item, "subinventory": subinventory, "lot_number": lot_number,
            "subinventory_type": subinventory_type, "group_by": group_by, "item_category": item_category}
    where = f"""
         WHERE {_ITEM_FILTER}
           AND {_CATEGORY_FILTER}
           AND (%(sub)s::text IS NULL OR UPPER(subinventory_code) = UPPER(%(sub)s::text))
           AND (%(lot)s::text IS NULL OR UPPER(lot_number) = UPPER(%(lot)s::text))
           AND (%(st)s::text  IS NULL OR subinventory_type = UPPER(%(st)s::text))
    """
    if group_by == "lot":
        sql = f"""
            SELECT item_code, item_desc, item_category, subinventory_code, subinventory_type, locator, lot_number,
                   lot_status, expiration_date, days_to_expiry, onhand_qty, uom
              FROM mart.inv_onhand_lot {where}
             ORDER BY item_code, expiration_date NULLS LAST
        """
    elif group_by == "subinventory":
        sql = f"""
            SELECT item_code, item_desc, subinventory_code, subinventory_type, uom,
                   SUM(onhand_qty) AS onhand_qty, COUNT(*) AS jml_lot
              FROM mart.inv_onhand_lot {where}
             GROUP BY item_code, item_desc, subinventory_code, subinventory_type, uom
             ORDER BY item_code, subinventory_code
        """
    else:
        sql = f"""
            SELECT item_code, item_desc, item_category, uom,
                   SUM(onhand_qty) FILTER (WHERE subinventory_type = 'GOOD')       AS qty_good,
                   SUM(onhand_qty) FILTER (WHERE subinventory_type = 'QUARANTINE') AS qty_quarantine,
                   SUM(onhand_qty) FILTER (WHERE subinventory_type = 'REJECT')     AS qty_reject,
                   SUM(onhand_qty)                                                  AS qty_total,
                   MIN(expiration_date) FILTER (WHERE days_to_expiry >= 0)         AS nearest_ed
              FROM mart.inv_onhand_lot {where}
             GROUP BY item_code, item_desc, item_category, uom
             ORDER BY item_code
        """
    params = {"item": _val(item), "sub": _val(subinventory), "lot": _val(lot_number), "st": _val(subinventory_type),
              "cat": _categories(item_category)}
    return _run(caller, "inv_onhand_lot", sql, params, "get_stock_onhand", args)


def get_stock_movement(caller: Caller, item: str | None = None, date_from: date | None = None,
                       date_to: date | None = None, transaction_type: str | None = None,
                       subinventory: str | None = None, group_by: str = "type") -> dict:
    args = {"item": item, "date_from": date_from, "date_to": date_to, "transaction_type": transaction_type,
            "subinventory": subinventory, "group_by": group_by}
    where = f"""
         WHERE {_ITEM_FILTER}
           AND (%(df)s::date  IS NULL OR txn_date >= %(df)s::date)
           AND (%(dt)s::date  IS NULL OR txn_date <= %(dt)s::date)
           AND (%(tt)s::text  IS NULL OR transaction_type ILIKE '%%' || %(tt)s::text || '%%')
           AND (%(sub)s::text IS NULL OR UPPER(subinventory_code) = UPPER(%(sub)s::text))
    """
    if group_by == "day":
        sql = f"""
            SELECT txn_date, item_code, uom, SUM(qty_in) AS qty_in, SUM(qty_out) AS qty_out, SUM(net_qty) AS net_qty
              FROM mart.inv_movement_daily {where}
             GROUP BY txn_date, item_code, uom ORDER BY txn_date, item_code
        """
    elif group_by == "month":
        sql = f"""
            SELECT period_start_date, period_name, item_code, uom,
                   SUM(qty_in) AS qty_in, SUM(qty_out) AS qty_out, SUM(net_qty) AS net_qty
              FROM mart.inv_movement_daily {where}
             GROUP BY period_start_date, period_name, item_code, uom ORDER BY period_start_date, item_code
        """
    elif group_by == "item":
        sql = f"""
            SELECT item_code, MAX(item_desc) AS item_desc, uom,
                   SUM(qty_in) AS qty_in, SUM(qty_out) AS qty_out, SUM(net_qty) AS net_qty
              FROM mart.inv_movement_daily {where}
             GROUP BY item_code, uom ORDER BY qty_out DESC
        """
    else:
        sql = f"""
            SELECT transaction_type, uom, SUM(qty_in) AS qty_in, SUM(qty_out) AS qty_out,
                   SUM(txn_count) AS jml_transaksi
              FROM mart.inv_movement_daily {where}
             GROUP BY transaction_type, uom ORDER BY transaction_type
        """
    params = {"item": _val(item), "df": date_from, "dt": date_to, "tt": _val(transaction_type),
              "sub": _val(subinventory)}
    return _run(caller, "inv_movement_daily", sql, params, "get_stock_movement", args)
