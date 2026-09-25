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
               days_on_hold, currency_code, invoice_amount_entered, invoice_amount_idr, invoice_found
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


# ── PO / PR (phase 2) ────────────────────────────────────────────────────────

def get_po_outstanding(caller: Caller, supplier: str | None = None, item: str | None = None,
                       po_number: str | None = None, late_only: bool = False,
                       group_by: str = "none") -> dict:
    args = {"supplier": supplier, "item": item, "po_number": po_number, "late_only": late_only, "group_by": group_by}
    where = f"""
         WHERE (%(s)s::text  IS NULL OR vendor_name ILIKE %(s)s::text)
           AND (%(po)s::text IS NULL OR UPPER(po_number) = UPPER(%(po)s::text))
           AND (NOT %(late)s::boolean OR delivery_status = 'Terlambat')
           AND {_ITEM_FILTER}
    """
    if group_by == "supplier":
        sql = f"""
            SELECT vendor_num, vendor_name, COUNT(DISTINCT po_number) AS jml_po, COUNT(*) AS jml_shipment,
                   COUNT(*) FILTER (WHERE delivery_status = 'Terlambat') AS jml_terlambat,
                   SUM(amount_outstanding_idr) AS outstanding_idr
              FROM mart.po_outstanding {where}
             GROUP BY vendor_num, vendor_name ORDER BY outstanding_idr DESC
        """
    else:
        sql = f"""
            SELECT po_number, release_num, line_num, shipment_num, po_date, vendor_name, item_code, item_desc, uom,
                   qty_ordered, qty_received, qty_outstanding, currency_code, unit_price_entered,
                   amount_outstanding_entered, amount_outstanding_idr, due_date, days_late, delivery_status
              FROM mart.po_outstanding {where}
             ORDER BY due_date NULLS LAST, po_number, line_num
        """
    params = {"s": _like(supplier), "po": _val(po_number), "late": bool(late_only), "item": _val(item)}
    return _run(caller, "po_outstanding", sql, params, "get_po_outstanding", args)


def get_po_match_status(caller: Caller, po_number: str | None = None, supplier: str | None = None,
                        item: str | None = None, status: str | None = None, group_by: str = "none") -> dict:
    """"PO ini sudah ditagih belum?" and uninvoiced receipts. status matches
    match_status as a prefix, case-insensitively (e.g. "Diterima")."""
    args = {"po_number": po_number, "supplier": supplier, "item": item, "status": status, "group_by": group_by}
    where = f"""
         WHERE (%(po)s::text IS NULL OR UPPER(po_number) = UPPER(%(po)s::text))
           AND (%(s)s::text  IS NULL OR vendor_name ILIKE %(s)s::text)
           AND (%(st)s::text IS NULL OR UPPER(match_status) LIKE UPPER(%(st)s::text) || '%%')
           AND {_ITEM_FILTER}
    """
    if group_by == "supplier":
        sql = f"""
            SELECT vendor_name, match_status, COUNT(DISTINCT po_number) AS jml_po, COUNT(*) AS jml_distribusi,
                   SUM(amount_received_not_billed_idr) AS diterima_belum_ditagih_idr,
                   SUM(amount_billed_idr) AS sudah_ditagih_idr
              FROM mart.po_receipt_vs_invoice {where}
             GROUP BY vendor_name, match_status ORDER BY vendor_name, match_status
        """
    elif group_by == "status":
        sql = f"""
            SELECT match_status, COUNT(DISTINCT po_number) AS jml_po, COUNT(*) AS jml_distribusi,
                   SUM(amount_received_not_billed_idr) AS diterima_belum_ditagih_idr
              FROM mart.po_receipt_vs_invoice {where}
             GROUP BY match_status ORDER BY 2 DESC
        """
    else:
        sql = f"""
            SELECT po_number, release_num, line_num, shipment_num, distribution_num, vendor_name, item_code,
                   item_desc, uom, qty_ordered, qty_received, qty_billed, qty_received_not_billed,
                   amount_received_not_billed_idr, match_type, match_status, invoice_count, last_invoice_num,
                   last_invoice_date, currency_code
              FROM mart.po_receipt_vs_invoice {where}
             ORDER BY po_number, line_num, shipment_num, distribution_num
        """
    params = {"po": _val(po_number), "s": _like(supplier), "st": _val(status), "item": _val(item)}
    return _run(caller, "po_receipt_vs_invoice", sql, params, "get_po_match_status", args)


def get_pr_pending(caller: Caller, person: str | None = None, item: str | None = None,
                   pr_number: str | None = None, min_days_waiting: int | None = None,
                   group_by: str = "none") -> dict:
    args = {"person": person, "item": item, "pr_number": pr_number, "min_days_waiting": min_days_waiting,
            "group_by": group_by}
    where = f"""
         WHERE (%(p)s::text  IS NULL OR preparer ILIKE %(p)s::text OR requester ILIKE %(p)s::text)
           AND (%(pr)s::text IS NULL OR UPPER(pr_number) = UPPER(%(pr)s::text))
           AND (%(d)s::int   IS NULL OR days_waiting >= %(d)s::int)
           AND {_ITEM_FILTER}
    """
    if group_by == "preparer":
        sql = f"""
            SELECT preparer, COUNT(DISTINCT pr_number) AS jml_pr, COUNT(*) AS jml_baris,
                   MAX(days_waiting) AS terlama_hari, SUM(amount_idr) AS nilai_idr
              FROM mart.pr_pending {where}
             GROUP BY preparer ORDER BY jml_baris DESC
        """
    else:
        sql = f"""
            SELECT pr_number, line_num, pr_date, approved_date, days_waiting, preparer, requester, item_code,
                   item_desc, uom, quantity, currency_code, unit_price_entered, amount_idr, need_by_date,
                   need_by_passed, suggested_vendor
              FROM mart.pr_pending {where}
             ORDER BY days_waiting DESC, pr_number, line_num
        """
    params = {"p": _like(person), "pr": _val(pr_number), "d": min_days_waiting, "item": _val(item)}
    return _run(caller, "pr_pending", sql, params, "get_pr_pending", args)


def get_inventory_value(caller: Caller, item: str | None = None, item_category=None,
                        subinventory_type: str | None = None, group_by: str = "category") -> dict:
    args = {"item": item, "item_category": item_category, "subinventory_type": subinventory_type,
            "group_by": group_by}
    where = f"""
         WHERE {_ITEM_FILTER}
           AND {_CATEGORY_FILTER}
           AND (%(st)s::text IS NULL OR subinventory_type = UPPER(%(st)s::text))
    """
    if group_by == "item":
        sql = f"""
            SELECT item_code, item_desc, item_category, uom, SUM(onhand_qty) AS onhand_qty,
                   MAX(unit_cost_idr) AS unit_cost_idr, SUM(value_idr) AS value_idr,
                   MAX(cost_period_code) AS cost_period, BOOL_AND(has_cost) AS has_cost
              FROM mart.inv_valuation {where}
             GROUP BY item_code, item_desc, item_category, uom ORDER BY value_idr DESC NULLS LAST
        """
    elif group_by == "subinventory_type":
        sql = f"""
            SELECT subinventory_type, COUNT(DISTINCT item_code) AS jml_item, SUM(value_idr) AS value_idr,
                   COUNT(*) FILTER (WHERE NOT has_cost) AS baris_tanpa_biaya
              FROM mart.inv_valuation {where}
             GROUP BY subinventory_type ORDER BY value_idr DESC NULLS LAST
        """
    else:
        sql = f"""
            SELECT COALESCE(item_category, '(tanpa kategori)') AS item_category, COUNT(DISTINCT item_code) AS jml_item,
                   SUM(value_idr) AS value_idr,
                   COUNT(DISTINCT item_code) FILTER (WHERE NOT has_cost) AS item_tanpa_biaya,
                   MAX(cost_period_code) AS cost_period_terbaru
              FROM mart.inv_valuation {where}
             GROUP BY 1 ORDER BY value_idr DESC NULLS LAST
        """
    params = {"item": _val(item), "cat": _categories(item_category), "st": _val(subinventory_type)}
    return _run(caller, "inv_valuation", sql, params, "get_inventory_value", args)


# ── OM / AR (phase 3) ────────────────────────────────────────────────────────

def _period_range(period: str | None) -> tuple:
    """'2026' -> whole year, '2026-03' -> one month, None -> no filter."""
    import re as _re
    if not period:
        return None, None
    m = _re.match(r"^\s*(\d{4})(?:-(\d{1,2}))?\s*$", str(period))
    if not m:
        raise sql_guard.SqlRejected(f"Format periode '{period}' tidak dikenal — pakai YYYY atau YYYY-MM.")
    y = int(m.group(1))
    if m.group(2):
        mo = int(m.group(2))
        start = date(y, mo, 1)
        end = date(y + (mo == 12), mo % 12 + 1, 1)
    else:
        start, end = date(y, 1, 1), date(y + 1, 1, 1)
    return start, end


def get_ar_aging(caller: Caller, customer: str | None = None, min_days_overdue: int | None = None,
                 currency: str | None = None, group_by: str = "customer") -> dict:
    args = {"customer": customer, "min_days_overdue": min_days_overdue, "currency": currency, "group_by": group_by}
    params = {"s": _like(customer), "d": min_days_overdue, "c": _val(currency)}
    where = """
        WHERE (%(d)s::int  IS NULL OR days_overdue >= %(d)s::int)
          AND (%(s)s::text IS NULL OR customer_name ILIKE %(s)s::text)
          AND (%(c)s::text IS NULL OR UPPER(currency_code) = UPPER(%(c)s::text))
    """
    if group_by == "bucket":
        sql = f"""
            SELECT aging_bucket, COUNT(*) AS jml_invoice, COUNT(DISTINCT customer_num) AS jml_customer,
                   SUM(amount_remaining_idr) AS total_idr
              FROM mart.ar_aging {where}
             GROUP BY aging_bucket, aging_bucket_order ORDER BY aging_bucket_order
        """
    elif group_by == "customer_bucket":
        sql = f"""
            SELECT customer_num, customer_name, aging_bucket, COUNT(*) AS jml_invoice,
                   SUM(amount_remaining_idr) AS total_idr
              FROM mart.ar_aging {where}
             GROUP BY customer_num, customer_name, aging_bucket, aging_bucket_order
             ORDER BY customer_name, aging_bucket_order
        """
    else:
        sql = f"""
            SELECT customer_num, customer_name,
                   SUM(amount_remaining_idr) FILTER (WHERE aging_bucket = 'Current') AS current_idr,
                   SUM(amount_remaining_idr) FILTER (WHERE aging_bucket = '1-30')    AS d1_30_idr,
                   SUM(amount_remaining_idr) FILTER (WHERE aging_bucket = '31-60')   AS d31_60_idr,
                   SUM(amount_remaining_idr) FILTER (WHERE aging_bucket = '61-90')   AS d61_90_idr,
                   SUM(amount_remaining_idr) FILTER (WHERE aging_bucket = '>90')     AS over_90_idr,
                   SUM(amount_remaining_idr)                                          AS total_idr,
                   COUNT(*)                                                           AS jml_invoice
              FROM mart.ar_aging {where}
             GROUP BY customer_num, customer_name
             ORDER BY total_idr DESC
        """
    return _run(caller, "ar_aging", sql, params, "get_ar_aging", args)


def get_ar_open_invoices(caller: Caller, customer: str | None = None, invoice_num: str | None = None,
                         min_days_overdue: int | None = None, due_from: date | None = None,
                         due_to: date | None = None, currency: str | None = None) -> dict:
    args = {"customer": customer, "invoice_num": invoice_num, "min_days_overdue": min_days_overdue,
            "due_from": due_from, "due_to": due_to, "currency": currency}
    sql = """
        SELECT customer_name, trx_number, class, trx_type, trx_date, due_date, days_overdue, aging_bucket,
               so_number, currency_code, amount_remaining_entered, amount_remaining_idr, fx_rate_used
          FROM mart.ar_aging
         WHERE (%(s)s::text   IS NULL OR customer_name ILIKE %(s)s::text)
           AND (%(inv)s::text IS NULL OR UPPER(trx_number) = UPPER(%(inv)s::text))
           AND (%(d)s::int    IS NULL OR days_overdue >= %(d)s::int)
           AND (%(df)s::date  IS NULL OR due_date >= %(df)s::date)
           AND (%(dt)s::date  IS NULL OR due_date <= %(dt)s::date)
           AND (%(c)s::text   IS NULL OR UPPER(currency_code) = UPPER(%(c)s::text))
         ORDER BY due_date, customer_name, trx_number
    """
    params = {"s": _like(customer), "inv": _val(invoice_num), "d": min_days_overdue,
              "df": due_from, "dt": due_to, "c": _val(currency)}
    return _run(caller, "ar_aging", sql, params, "get_ar_open_invoices", args)


def get_ar_receipts(caller: Caller, customer: str | None = None, receipt_number: str | None = None,
                    date_from: date | None = None, date_to: date | None = None,
                    application_status: str | None = None, include_reversed: bool = False,
                    group_by: str = "none") -> dict:
    args = {"customer": customer, "receipt_number": receipt_number, "date_from": date_from, "date_to": date_to,
            "application_status": application_status, "include_reversed": include_reversed, "group_by": group_by}
    where = """
         WHERE (%(s)s::text   IS NULL OR customer_name ILIKE %(s)s::text)
           AND (%(rn)s::text  IS NULL OR UPPER(receipt_number) = UPPER(%(rn)s::text))
           AND (%(df)s::date  IS NULL OR receipt_date >= %(df)s::date)
           AND (%(dt)s::date  IS NULL OR receipt_date <= %(dt)s::date)
           AND (%(st)s::text  IS NULL OR application_status = UPPER(%(st)s::text))
           AND (%(rev)s::boolean OR NOT is_reversed)
    """
    # All application rows of a receipt sum to the receipt amount, so these
    # totals never double count a receipt spread over several invoices.
    totals = """
                   SUM(amount_idr) FILTER (WHERE application_status = 'APP')   AS diaplikasikan_idr,
                   SUM(amount_idr) FILTER (WHERE application_status = 'UNAPP') AS belum_diaplikasikan_idr,
                   SUM(amount_idr) FILTER (WHERE application_status NOT IN ('APP', 'UNAPP')) AS on_account_lainnya_idr,
                   SUM(amount_idr)                                             AS total_idr"""
    if group_by == "customer":
        sql = f"""
            SELECT customer_name, COUNT(DISTINCT cash_receipt_id) AS jml_penerimaan, {totals}
              FROM mart.ar_receipt {where}
             GROUP BY customer_name ORDER BY total_idr DESC
        """
    elif group_by == "month":
        sql = f"""
            SELECT receipt_period_start_date, receipt_period_name, COUNT(DISTINCT cash_receipt_id) AS jml_penerimaan,
                   {totals}
              FROM mart.ar_receipt {where}
             GROUP BY receipt_period_start_date, receipt_period_name ORDER BY receipt_period_start_date
        """
    else:
        sql = f"""
            SELECT receipt_number, receipt_date, customer_name, receipt_method, receipt_status, currency_code,
                   receipt_amount_entered, receipt_amount_idr, application_status_desc, applied_invoice_num,
                   amount_entered, amount_idr, is_reversed
              FROM mart.ar_receipt {where}
             ORDER BY receipt_date DESC, receipt_number, application_status
        """
    params = {"s": _like(customer), "rn": _val(receipt_number), "df": date_from, "dt": date_to,
              "st": _val(application_status), "rev": bool(include_reversed)}
    return _run(caller, "ar_receipt", sql, params, "get_ar_receipts", args)


def get_so_backlog(caller: Caller, customer: str | None = None, item: str | None = None,
                   order_number: str | None = None, business_type: str | None = None,
                   late_only: bool = False, ordered_from: date | None = None, ordered_to: date | None = None,
                   group_by: str = "none") -> dict:
    """ordered_from/ordered_to exist because most of the backlog is old: on
    first load 364 of 468 open lines came from 2020–2024 orders never shipped
    or closed. "Backlog bulan ini" should be answerable without them."""
    args = {"customer": customer, "item": item, "order_number": order_number, "business_type": business_type,
            "late_only": late_only, "ordered_from": ordered_from, "ordered_to": ordered_to, "group_by": group_by}
    where = f"""
         WHERE (%(s)s::text  IS NULL OR customer_name ILIKE %(s)s::text)
           AND (%(on)s::text IS NULL OR order_number = %(on)s::text)
           AND (%(bt)s::text IS NULL OR UPPER(business_type) = UPPER(%(bt)s::text))
           AND (NOT %(late)s::boolean OR delivery_status = 'Terlambat')
           AND (%(of)s::date IS NULL OR ordered_date >= %(of)s::date)
           AND (%(ot)s::date IS NULL OR ordered_date <= %(ot)s::date)
           AND {_ITEM_FILTER}
    """
    if group_by == "customer":
        sql = f"""
            SELECT customer_name, COUNT(DISTINCT order_number) AS jml_order, COUNT(*) AS jml_baris,
                   COUNT(*) FILTER (WHERE delivery_status = 'Terlambat') AS jml_terlambat,
                   SUM(amount_to_ship_idr) AS belum_dikirim_idr
              FROM mart.so_backlog {where}
             GROUP BY customer_name ORDER BY belum_dikirim_idr DESC NULLS LAST
        """
    elif group_by == "year":
        sql = f"""
            SELECT EXTRACT(YEAR FROM ordered_date)::int AS tahun_order, COUNT(DISTINCT order_number) AS jml_order,
                   COUNT(*) AS jml_baris, SUM(amount_to_ship_idr) AS belum_dikirim_idr
              FROM mart.so_backlog {where}
             GROUP BY 1 ORDER BY 1
        """
    elif group_by == "item":
        sql = f"""
            SELECT item_code, MAX(item_desc) AS item_desc, uom, SUM(qty_to_ship) AS qty_belum_dikirim,
                   SUM(amount_to_ship_idr) AS belum_dikirim_idr, COUNT(DISTINCT order_number) AS jml_order
              FROM mart.so_backlog {where}
             GROUP BY item_code, uom ORDER BY belum_dikirim_idr DESC NULLS LAST
        """
    else:
        sql = f"""
            SELECT order_number, line_number, shipment_number, business_type, ordered_date, customer_name,
                   item_code, item_desc, uom, ordered_qty, shipped_qty, qty_to_ship, currency_code,
                   amount_to_ship_entered, amount_to_ship_idr, due_date, days_late, delivery_status, line_status
              FROM mart.so_backlog {where}
             ORDER BY due_date NULLS LAST, order_number, line_number
        """
    params = {"s": _like(customer), "on": _val(order_number), "bt": _val(business_type), "late": bool(late_only),
              "of": ordered_from, "ot": ordered_to, "item": _val(item)}
    return _run(caller, "so_backlog", sql, params, "get_so_backlog", args)


def get_so_shipment_status(caller: Caller, order_number: str | None = None, customer: str | None = None,
                           item: str | None = None, status: str | None = None) -> dict:
    args = {"order_number": order_number, "customer": customer, "item": item, "status": status}
    sql = f"""
        SELECT order_number, line_number, shipment_number, customer_name, item_code, item_desc, uom, ordered_qty,
               qty_shipped, qty_staged, qty_released_to_warehouse, qty_ready_to_release, qty_backordered,
               shipment_status, delivery_names, last_ship_confirm_date, lot_numbers, schedule_ship_date
          FROM mart.so_shipment_status
         WHERE (%(on)s::text IS NULL OR order_number = %(on)s::text)
           AND (%(s)s::text  IS NULL OR customer_name ILIKE %(s)s::text)
           AND (%(st)s::text IS NULL OR UPPER(shipment_status) LIKE UPPER(%(st)s::text) || '%%')
           AND {_ITEM_FILTER}
         ORDER BY order_number DESC, line_number, shipment_number
    """
    params = {"on": _val(order_number), "s": _like(customer), "st": _val(status), "item": _val(item)}
    return _run(caller, "so_shipment_status", sql, params, "get_so_shipment_status", args)


def get_sales_by_customer(caller: Caller, customer: str | None = None, item: str | None = None,
                          item_category=None, period: str | None = None, business_type: str | None = None,
                          group_by: str = "customer") -> dict:
    args = {"customer": customer, "item": item, "item_category": item_category, "period": period,
            "business_type": business_type, "group_by": group_by}
    start, end = _period_range(period)
    where = f"""
         WHERE (%(s)s::text  IS NULL OR customer_name ILIKE %(s)s::text)
           AND (%(bt)s::text IS NULL OR UPPER(business_type) = UPPER(%(bt)s::text))
           AND (%(p0)s::date IS NULL OR period_start_date >= %(p0)s::date)
           AND (%(p1)s::date IS NULL OR period_start_date <  %(p1)s::date)
           AND {_ITEM_FILTER}
           AND {_CATEGORY_FILTER}
    """
    groups = {
        "customer": ("customer_num, customer_name", "customer_name, customer_num"),
        "item": ("item_code, uom", "item_code, MAX(item_desc) AS item_desc, uom"),
        "month": ("period_start_date, period_name", "period_start_date, period_name"),
        "customer_item": ("customer_name, item_code, uom", "customer_name, item_code, MAX(item_desc) AS item_desc, uom"),
        "business_type": ("business_type", "business_type"),
    }
    gcols, scols = groups.get(group_by, groups["customer"])
    qty = "SUM(quantity) AS qty, " if group_by in ("item", "customer_item") else ""
    order = "period_start_date" if group_by == "month" else "nilai_idr DESC"
    sql = f"""
        SELECT {scols}, {qty}SUM(amount_idr) AS nilai_idr, SUM(credit_memo_idr) AS credit_memo_idr,
               SUM(invoice_count) AS jml_invoice
          FROM mart.sales_by_customer_item_month {where}
         GROUP BY {gcols} ORDER BY {order}
    """
    params = {"s": _like(customer), "bt": _val(business_type), "p0": start, "p1": end, "item": _val(item),
              "cat": _categories(item_category)}
    return _run(caller, "sales_by_customer_item_month", sql, params, "get_sales_by_customer", args)


# ── OPM batches (phase 4) ────────────────────────────────────────────────────

_BATCH_STATUS_CODES = {"pending": 1, "wip": 2, "completed": 3, "closed": 4, "cancelled": -1}


def _status_code(status):
    if status is None or str(status).strip() == "":
        return None
    s = str(status).strip().lower()
    if s.lstrip("-").isdigit():
        return int(s)
    if s not in _BATCH_STATUS_CODES:
        raise sql_guard.SqlRejected("Status batch tidak dikenal — pakai Pending, WIP, Completed, Closed, atau Cancelled.")
    return _BATCH_STATUS_CODES[s]


def get_batch_status(caller: Caller, batch_no: str | None = None, product: str | None = None,
                     status: str | None = None, date_from: date | None = None, date_to: date | None = None,
                     late_only: bool = False, group_by: str = "none") -> dict:
    """Batches by plan start date, as the Production dashboard filters them."""
    args = {"batch_no": batch_no, "product": product, "status": status, "date_from": date_from, "date_to": date_to,
            "late_only": late_only, "group_by": group_by}
    where = """
         WHERE (%(bn)s::text  IS NULL OR batch_no = %(bn)s::text)
           AND (%(p)s::text   IS NULL OR UPPER(product_code) = UPPER(%(p)s::text)
                                      OR product_desc ILIKE '%%' || %(p)s::text || '%%')
           AND (%(st)s::int   IS NULL OR batch_status = %(st)s::int)
           AND (%(df)s::date  IS NULL OR plan_start_date >= %(df)s::date)
           AND (%(dt)s::date  IS NULL OR plan_start_date <= %(dt)s::date)
           AND (NOT %(late)s::boolean OR schedule_status IN ('Selesai terlambat', 'Belum selesai, lewat rencana'))
    """
    if group_by == "status":
        sql = f"""
            SELECT batch_status_desc, COUNT(*) AS jml_batch FROM mart.batch_status {where}
             GROUP BY batch_status_desc ORDER BY 2 DESC
        """
    elif group_by == "schedule":
        # Same definition as the Production dashboard's Schedule Adherence:
        # completed batches, on time when actual <= planned completion.
        sql = f"""
            SELECT COUNT(*) FILTER (WHERE actual_cmplt_date IS NOT NULL AND plan_cmplt_date IS NOT NULL) AS batch_selesai,
                   COUNT(*) FILTER (WHERE on_time)                                                AS tepat_waktu,
                   ROUND(100.0 * COUNT(*) FILTER (WHERE on_time)
                         / NULLIF(COUNT(*) FILTER (WHERE actual_cmplt_date IS NOT NULL AND plan_cmplt_date IS NOT NULL), 0), 1)
                                                                                                  AS on_time_pct,
                   ROUND(AVG(completion_delay_days) FILTER (WHERE actual_cmplt_date IS NOT NULL), 1) AS rata2_delay_hari,
                   COUNT(*) FILTER (WHERE schedule_status = 'Belum selesai, lewat rencana')       AS berjalan_lewat_rencana
              FROM mart.batch_status {where}
        """
    elif group_by == "product":
        sql = f"""
            SELECT product_code, MAX(product_desc) AS product_desc, product_uom, COUNT(*) AS jml_batch,
                   SUM(product_plan_qty) AS plan_qty, SUM(product_actual_qty) AS actual_qty,
                   COUNT(*) FILTER (WHERE on_time) AS tepat_waktu
              FROM mart.batch_status {where}
             GROUP BY product_code, product_uom ORDER BY jml_batch DESC
        """
    elif group_by == "month":
        sql = f"""
            SELECT plan_period_start_date, plan_period_name, COUNT(*) AS jml_batch,
                   COUNT(*) FILTER (WHERE batch_status IN (3, 4)) AS selesai,
                   COUNT(*) FILTER (WHERE batch_status = -1) AS batal,
                   COUNT(*) FILTER (WHERE on_time) AS tepat_waktu
              FROM mart.batch_status {where}
             GROUP BY plan_period_start_date, plan_period_name ORDER BY plan_period_start_date
        """
    else:
        sql = f"""
            SELECT batch_no, batch_status_desc, formula, product_code, product_desc, product_uom, product_plan_qty,
                   product_actual_qty, yield_pct, plan_start_date, actual_start_date, plan_cmplt_date,
                   actual_cmplt_date, completion_delay_days, schedule_status
              FROM mart.batch_status {where}
             ORDER BY plan_start_date DESC, batch_no
        """
    params = {"bn": _val(batch_no), "p": _val(product), "st": _status_code(status), "df": date_from, "dt": date_to,
              "late": bool(late_only)}
    return _run(caller, "batch_status", sql, params, "get_batch_status", args)


def get_batch_yield(caller: Caller, product: str | None = None, batch_no: str | None = None,
                    date_from: date | None = None, date_to: date | None = None,
                    below_pct: float | None = None, group_by: str = "product") -> dict:
    """Yield of completed/closed batches (status 3, 4) — the Production
    dashboard's definition: product actual ÷ product plan."""
    args = {"product": product, "batch_no": batch_no, "date_from": date_from, "date_to": date_to,
            "below_pct": below_pct, "group_by": group_by}
    where = """
         WHERE batch_status IN (3, 4)
           AND line_type = 1
           AND (%(bn)s::text  IS NULL OR batch_no = %(bn)s::text)
           AND (%(p)s::text   IS NULL OR UPPER(item_code) = UPPER(%(p)s::text)
                                      OR item_desc ILIKE '%%' || %(p)s::text || '%%')
           AND (%(df)s::date  IS NULL OR plan_start_date >= %(df)s::date)
           AND (%(dt)s::date  IS NULL OR plan_start_date <= %(dt)s::date)
    """
    if group_by == "batch":
        sql = f"""
            SELECT batch_no, item_code, item_desc, uom, plan_qty, standard_qty, actual_qty, variance_qty, yield_pct,
                   plan_start_date, actual_cmplt_date
              FROM mart.batch_yield_variance {where}
               AND (%(b)s::numeric IS NULL OR yield_pct < %(b)s::numeric)
             ORDER BY yield_pct NULLS LAST, batch_no
        """
    elif group_by == "month":
        sql = f"""
            SELECT plan_period_start_date, plan_period_name, COUNT(DISTINCT batch_id) AS jml_batch,
                   ROUND(100.0 * SUM(actual_qty) / NULLIF(SUM(plan_qty), 0), 1) AS yield_pct
              FROM mart.batch_yield_variance {where}
             GROUP BY plan_period_start_date, plan_period_name ORDER BY plan_period_start_date
        """
    else:
        sql = f"""
            SELECT * FROM (
                SELECT item_code, MAX(item_desc) AS item_desc, uom, COUNT(DISTINCT batch_id) AS jml_batch,
                       SUM(plan_qty) AS plan_qty, SUM(actual_qty) AS actual_qty,
                       ROUND(100.0 * SUM(actual_qty) / NULLIF(SUM(plan_qty), 0), 1) AS yield_pct,
                       MIN(yield_pct) AS yield_min_pct, MAX(yield_pct) AS yield_max_pct
                  FROM mart.batch_yield_variance {where}
                 GROUP BY item_code, uom
            ) t WHERE (%(b)s::numeric IS NULL OR yield_pct < %(b)s::numeric)
             ORDER BY jml_batch DESC
        """
    params = {"bn": _val(batch_no), "p": _val(product), "df": date_from, "dt": date_to, "b": below_pct}
    return _run(caller, "batch_yield_variance", sql, params, "get_batch_yield", args)


def get_batch_material_usage(caller: Caller, batch_no: str | None = None, ingredient: str | None = None,
                             lot_number: str | None = None, over_pct: float | None = None,
                             group_by: str = "none") -> dict:
    """Ingredient usage per batch and lot — also the traceability question
    'lot X dipakai di batch mana' (lot_number without batch_no)."""
    args = {"batch_no": batch_no, "ingredient": ingredient, "lot_number": lot_number, "over_pct": over_pct,
            "group_by": group_by}
    where = """
         WHERE (%(bn)s::text  IS NULL OR batch_no = %(bn)s::text)
           AND (%(i)s::text   IS NULL OR UPPER(item_code) = UPPER(%(i)s::text)
                                      OR item_desc ILIKE '%%' || %(i)s::text || '%%')
           AND (%(lot)s::text IS NULL OR UPPER(lot_number) = UPPER(%(lot)s::text))
           AND (%(o)s::numeric IS NULL OR ABS(line_variance_pct) >= %(o)s::numeric)
    """
    if group_by == "ingredient":
        # Line-level quantities repeat on each lot row: count each line once.
        sql = f"""
            SELECT item_code, MAX(item_desc) AS item_desc, uom, COUNT(DISTINCT batch_id) AS jml_batch,
                   SUM(line_standard_qty) AS standard_qty, SUM(line_actual_qty) AS actual_qty,
                   ROUND(100.0 * (SUM(line_actual_qty) - SUM(line_standard_qty)) / NULLIF(SUM(line_standard_qty), 0), 1)
                                                                                     AS variance_pct
              FROM (SELECT DISTINCT ON (material_detail_id) * FROM mart.batch_material_usage {where}
                     ORDER BY material_detail_id) x
             GROUP BY item_code, uom ORDER BY jml_batch DESC
        """
    else:
        sql = f"""
            SELECT batch_no, batch_status_desc, product_code, item_code, item_desc, uom, line_standard_qty,
                   line_plan_qty, line_actual_qty, line_variance_pct, lot_number, lot_qty_consumed, last_txn_date
              FROM mart.batch_material_usage {where}
             ORDER BY batch_no DESC, item_code, lot_number
        """
    params = {"bn": _val(batch_no), "i": _val(ingredient), "lot": _val(lot_number), "o": over_pct}
    return _run(caller, "batch_material_usage", sql, params, "get_batch_material_usage", args)


# ── GL (phase 5) ─────────────────────────────────────────────────────────────

_MON = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def _gl_period_filter(period: str | None, ytd: bool = False) -> tuple[str, dict]:
    """period YYYY -> every period of that fiscal year (including the
    adjustment period, as the Financial Statement report's FY column does);
    YYYY-MM -> that month; with ytd -> months 1..MM of that year, adjustment
    period excluded (the report's YTD columns). MON-YY is accepted too."""
    import re as _re
    if not period:
        return "TRUE", {}
    p = str(period).strip().upper()
    m = _re.match(r"^([A-Z]{3})-(\d{2})$", p)
    if m and m.group(1) in _MON:
        year, month = 2000 + int(m.group(2)), _MON.index(m.group(1)) + 1
    else:
        m = _re.match(r"^(\d{4})(?:-(\d{1,2}))?$", p)
        if not m:
            raise sql_guard.SqlRejected(f"Format periode '{period}' tidak dikenal — pakai YYYY, YYYY-MM, atau JUL-26.")
        year, month = int(m.group(1)), int(m.group(2)) if m.group(2) else None
    if month is None:
        return "period_year = %(py)s", {"py": year}
    if ytd:
        return "period_year = %(py)s AND period_num <= %(pn)s AND NOT is_adjustment", {"py": year, "pn": month}
    return "period_year = %(py)s AND period_num = %(pn)s AND NOT is_adjustment", {"py": year, "pn": month}


_ACCOUNT_FILTER = """(%(acc)s::text IS NULL OR account_code LIKE %(acc)s::text || '%%'
                      OR account_desc ILIKE '%%' || %(acc)s::text || '%%')"""
_DEPT_FILTER = """(%(dept)s::text IS NULL OR dept_code = %(dept)s::text OR dept_desc ILIKE '%%' || %(dept)s::text || '%%')"""


def get_pl(caller: Caller, period: str, ytd: bool = False, department: str | None = None,
           compare_prior_year: bool = False, level: str = "line") -> dict:
    """Profit & loss in the Financial Statement report's layout: lines by
    section, then the report's subtotals (net sales, gross profit, profit
    before / after tax, total comprehensive income). compare_prior_year
    adds the same period one year earlier."""
    args = {"period": period, "ytd": ytd, "department": department, "compare_prior_year": compare_prior_year,
            "level": level}
    cond, params = _gl_period_filter(period, ytd)
    params.update({"dept": _val(department)})
    prior_cond = "FALSE"
    if compare_prior_year and "py" in params:
        prior_cond = cond.replace("%(py)s", "(%(py)s - 1)")
    grp = "section, section_order" if level == "section" else "section, section_order, line, line_order"
    sel = "section" if level == "section" else "section, line"
    sql = f"""
        WITH base AS (
            SELECT section, section_order, line, line_order,
                   SUM(amount) FILTER (WHERE {cond})       AS amount_idr,
                   SUM(amount) FILTER (WHERE {prior_cond}) AS amount_prior_year_idr
              FROM mart.pl_monthly
             WHERE ({cond} OR {prior_cond}) AND {_DEPT_FILTER}
             GROUP BY section, section_order, line, line_order
        ), lines AS (
            SELECT {sel}, MIN(section_order) AS so, MIN({'0' if level == 'section' else 'line_order'}) AS lo,
                   SUM(amount_idr) AS amount_idr, SUM(amount_prior_year_idr) AS amount_prior_year_idr
              FROM base WHERE section <> 'UNMAPPED' GROUP BY {grp}
        ), s AS (
            SELECT section, SUM(amount_idr) a, SUM(amount_prior_year_idr) p FROM base GROUP BY section
        ), tot AS (
            SELECT
              COALESCE(MAX(a) FILTER (WHERE section = 'SALES'), 0) AS sales,
              COALESCE(MAX(a) FILTER (WHERE section = 'COGS'), 0) AS cogs,
              COALESCE(MAX(a) FILTER (WHERE section = 'OPERATING EXPENSES'), 0) AS opex,
              COALESCE(MAX(a) FILTER (WHERE section = 'OTHER INCOME/EXPENSE'), 0) AS other,
              COALESCE(MAX(a) FILTER (WHERE section = 'TAX'), 0) AS tax,
              COALESCE(MAX(a) FILTER (WHERE section = 'OTHER COMPREHENSIVE INCOME'), 0) AS oci,
              COALESCE(MAX(p) FILTER (WHERE section = 'SALES'), 0) AS p_sales,
              COALESCE(MAX(p) FILTER (WHERE section = 'COGS'), 0) AS p_cogs,
              COALESCE(MAX(p) FILTER (WHERE section = 'OPERATING EXPENSES'), 0) AS p_opex,
              COALESCE(MAX(p) FILTER (WHERE section = 'OTHER INCOME/EXPENSE'), 0) AS p_other,
              COALESCE(MAX(p) FILTER (WHERE section = 'TAX'), 0) AS p_tax,
              COALESCE(MAX(p) FILTER (WHERE section = 'OTHER COMPREHENSIVE INCOME'), 0) AS p_oci,
              COALESCE(MAX(a) FILTER (WHERE section = 'UNMAPPED'), 0) AS unmapped
            FROM s
        )
        SELECT {'section' if level == 'section' else 'section, line'}, amount_idr, amount_prior_year_idr, so, lo
          FROM lines
        UNION ALL SELECT {"'TOTAL'" if level == 'section' else "'TOTAL', 'NET SALES'"}, sales, p_sales, 10, 1 FROM tot
        UNION ALL SELECT {"'TOTAL'" if level == 'section' else "'TOTAL', 'GROSS PROFIT'"}, sales - cogs, p_sales - p_cogs, 10, 2 FROM tot
        UNION ALL SELECT {"'TOTAL'" if level == 'section' else "'TOTAL', 'PROFIT BEFORE TAX'"}, sales - cogs - opex + other,
                         p_sales - p_cogs - p_opex + p_other, 10, 3 FROM tot
        UNION ALL SELECT {"'TOTAL'" if level == 'section' else "'TOTAL', 'PROFIT AFTER TAX'"}, sales - cogs - opex + other + tax,
                         p_sales - p_cogs - p_opex + p_other + p_tax, 10, 4 FROM tot
        UNION ALL SELECT {"'TOTAL'" if level == 'section' else "'TOTAL', 'TOTAL COMPREHENSIVE INCOME'"},
                         sales - cogs - opex + other + tax + oci, p_sales - p_cogs - p_opex + p_other + p_tax + p_oci, 10, 5 FROM tot
        UNION ALL SELECT {"'UNMAPPED'" if level == 'section' else "'UNMAPPED', 'AKUN BELUM TERPETAKAN (tidak masuk total)'"},
                         unmapped, NULL, 11, 1 FROM tot WHERE unmapped <> 0
        ORDER BY so, lo
    """
    return _run(caller, "pl_monthly", sql, params, "get_pl", args)


def get_trial_balance(caller: Caller, period: str, account: str | None = None, department: str | None = None,
                      statement: str | None = None, group_by: str = "account") -> dict:
    """Trial balance for one period (month or MON-YY). Balances in GL's
    debit-positive convention (begin, dr, cr, end) plus end_balance_fs in the
    statement's reading (liabilities/equity positive)."""
    args = {"period": period, "account": account, "department": department, "statement": statement,
            "group_by": group_by}
    cond, params = _gl_period_filter(period)
    if "pn" not in params:
        raise sql_guard.SqlRejected("Trial balance butuh satu periode bulan (YYYY-MM atau JUL-26), bukan setahun.")
    params.update({"acc": _val(account), "dept": _val(department), "st": _val(statement)})
    where = f"""
         WHERE {cond}
           AND {_ACCOUNT_FILTER}
           AND {_DEPT_FILTER}
           AND (%(st)s::text IS NULL OR statement = UPPER(%(st)s::text))
    """
    measures = """SUM(begin_balance) AS begin_balance, SUM(period_dr) AS period_dr, SUM(period_cr) AS period_cr,
                  SUM(end_balance) AS end_balance, SUM(end_balance_fs) AS end_balance_fs"""
    if group_by == "fs_line":
        sql = f"""
            SELECT statement, section, fs_line, {measures}
              FROM mart.gl_trial_balance {where}
             GROUP BY statement, section, section_order, fs_line, line_order
             ORDER BY statement, section_order, line_order
        """
    elif group_by == "department":
        sql = f"""
            SELECT dept_code, MAX(dept_desc) AS dept_desc, {measures}
              FROM mart.gl_trial_balance {where}
             GROUP BY dept_code ORDER BY dept_code
        """
    else:
        sql = f"""
            SELECT account_code, MAX(account_desc) AS account_desc, MAX(statement) AS statement,
                   MAX(fs_line) AS fs_line, {measures}
              FROM mart.gl_trial_balance {where}
             GROUP BY account_code ORDER BY account_code
        """
    return _run(caller, "gl_trial_balance", sql, params, "get_trial_balance", args)


def get_gl_journals(caller: Caller, period: str | None = None, date_from: date | None = None,
                    date_to: date | None = None, account: str | None = None, department: str | None = None,
                    source: str | None = None, category: str | None = None, text: str | None = None,
                    subledger_txn: str | None = None, min_amount: float | None = None,
                    group_by: str = "none") -> dict:
    """Posted journal lines of the last months (see GL_JOURNAL_MONTHS), with
    source, category and the subledger transaction behind each line."""
    args = {"period": period, "date_from": date_from, "date_to": date_to, "account": account,
            "department": department, "source": source, "category": category, "text": text,
            "subledger_txn": subledger_txn, "min_amount": min_amount, "group_by": group_by}
    cond, params = _gl_period_filter(period)
    params.update({"df": date_from, "dt": date_to, "acc": _val(account), "dept": _val(department),
                   "src": _val(source), "cat": _val(category), "txt": _val(text), "sub": _val(subledger_txn),
                   "min": min_amount})
    where = f"""
         WHERE {cond}
           AND (%(df)s::date IS NULL OR effective_date >= %(df)s::date)
           AND (%(dt)s::date IS NULL OR effective_date <= %(dt)s::date)
           AND {_ACCOUNT_FILTER}
           AND {_DEPT_FILTER}
           AND (%(src)s::text IS NULL OR je_source ILIKE %(src)s::text || '%%')
           AND (%(cat)s::text IS NULL OR je_category ILIKE %(cat)s::text || '%%')
           AND (%(txt)s::text IS NULL OR line_description ILIKE '%%' || %(txt)s::text || '%%'
                                      OR journal_name ILIKE '%%' || %(txt)s::text || '%%')
           AND (%(sub)s::text IS NULL OR UPPER(subledger_txn_number) = UPPER(%(sub)s::text))
           AND (%(min)s::numeric IS NULL OR ABS(net_idr) >= %(min)s::numeric)
    """
    if group_by == "source":
        sql = f"""
            SELECT je_source, je_category, COUNT(*) AS jml_baris, SUM(debit_idr) AS debit_idr,
                   SUM(credit_idr) AS credit_idr
              FROM mart.gl_journal_detail {where}
             GROUP BY je_source, je_category ORDER BY debit_idr DESC
        """
    elif group_by == "account":
        sql = f"""
            SELECT account_code, MAX(account_desc) AS account_desc, COUNT(*) AS jml_baris,
                   SUM(debit_idr) AS debit_idr, SUM(credit_idr) AS credit_idr, SUM(net_idr) AS net_idr
              FROM mart.gl_journal_detail {where}
             GROUP BY account_code ORDER BY ABS(SUM(net_idr)) DESC
        """
    else:
        sql = f"""
            SELECT effective_date, period_name, je_source, je_category, journal_name, account_code, account_desc,
                   dept_code, line_description, debit_idr, credit_idr, currency_code, subledger_entity,
                   subledger_txn_number, subledger_txn_count
              FROM mart.gl_journal_detail {where}
             ORDER BY effective_date DESC, je_header_id, je_line_num
        """
    return _run(caller, "gl_journal_detail", sql, params, "get_gl_journals", args)
