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
from app.services.ebs_mart.constants import MARTS, SA_PREFIX


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
        # sa_* are left out even for the allowlist: they are read through the
        # sa_* tools, never run_sql, so offering their columns only invites a
        # query that will be refused.
        if name.startswith(SA_PREFIX) or not caller.can_read(name) or not MARTS.get(name, {}).get("built"):
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
    sa = [m for m in guarded.tables if m.startswith(SA_PREFIX)]
    if sa:
        # System Administration data is reachable through the sa_* tools only,
        # even for the allowlist: run_sql reads as llm_ro, which holds no
        # grant on mart.sa_* anyway (third layer) — refuse before trying.
        e = access.AccessDenied(f"mart.{sa[0]} tidak bisa dibaca lewat run_sql. "
                                "Data System Administration hanya lewat tool sa_* (tim IT tertentu).")
        query.log_call(caller, tool="run_sql", question=question, sql=sql, marts=guarded.tables,
                       status="DENIED", error=str(e))
        raise e
    for m in guarded.tables:
        try:
            access.require(caller, m)
        except access.AccessDenied as e:
            query.log_call(caller, tool="run_sql", question=question, sql=sql, marts=guarded.tables,
                           status="DENIED", error=str(e))
            raise
    qty = [m for m in guarded.tables if caller.level(m) == "qty"]
    if qty:
        # Quantity-only access: the query may not read a money column at all
        # (aliasing one would slip past the result masking in query.run).
        import sqlglot
        from sqlglot import exp
        from app.services.ebs_mart.policy import is_money
        tree = sqlglot.parse_one(guarded.sql, read="postgres")
        star = any(True for _ in tree.find_all(exp.Star))
        money = sorted({c.name for c in tree.find_all(exp.Column) if is_money(c.name)})
        if star or money:
            e = access.AccessDenied(
                f"Akses Anda untuk mart.{', mart.'.join(qty)} hanya kuantitas. "
                + ("Sebutkan kolom satu per satu (tanpa SELECT *). " if star else "")
                + (f"Kolom nilai/harga tidak boleh dipakai: {', '.join(money)}." if money else ""))
            query.log_call(caller, tool="run_sql", question=question, sql=sql, marts=guarded.tables,
                           status="DENIED", error=str(e))
            raise e
    return query.run(caller, guarded.sql, None, tool="run_sql", marts=guarded.tables, question=question,
                     args={"sql": sql})


def get_data_freshness(caller: Caller, domain: str | None = None) -> dict:
    """Which marts this caller can read, when each was last loaded, and how
    many rows it holds — for "data per kapan?" and for the model to check
    before trusting an empty answer."""
    out = []
    marts = [m for m in caller.readable_marts()
             if not domain or MARTS[m]["domain"].upper() == domain.strip().upper()]
    # sa_* marts are counted over the SA reader: llm_ro cannot see them.
    for reader, names in ((query._reader, [m for m in marts if not m.startswith(SA_PREFIX)]),
                          (query._sa_reader, [m for m in marts if m.startswith(SA_PREFIX)])):
        if not names:
            continue
        conn = reader()
        try:
            with conn.cursor() as cur:
                for name in names:
                    cur.execute(f"SELECT COUNT(*) FROM mart.{name}")
                    out.append({"mart": f"mart.{name}", "domain": MARTS[name]["domain"],
                                "row_count": cur.fetchone()[0], "as_of": query.as_of([name])})
            conn.rollback()
        finally:
            conn.close()
    query.log_call(caller, tool="get_data_freshness", args={"domain": domain}, row_count=len(out), status="OK")
    return {"marts": out}


# ── AP ───────────────────────────────────────────────────────────────────────

def ap_get_aging(caller: Caller, supplier: str | None = None, min_days_overdue: int | None = None,
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
    return _run(caller, "ap_open_invoice", sql, params, "ap_get_aging", args)


def ap_get_open_invoices(caller: Caller, supplier: str | None = None, invoice_num: str | None = None,
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
    return _run(caller, "ap_open_invoice", sql, params, "ap_get_open_invoices", args)


def ap_get_payments(caller: Caller, supplier: str | None = None, invoice_num: str | None = None,
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
    return _run(caller, "ap_payment_history", sql, params, "ap_get_payments", args)


def ap_get_holds(caller: Caller, supplier: str | None = None, hold_code: str | None = None) -> dict:
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
                "ap_get_holds", args)


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


def inv_get_expiring_lots(caller: Caller, days: int = 90, item: str | None = None,
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
    return _run(caller, "inv_onhand_lot", sql, params, "inv_get_expiring_lots", args)


def inv_get_onhand(caller: Caller, item: str | None = None, subinventory: str | None = None,
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
    return _run(caller, "inv_onhand_lot", sql, params, "inv_get_onhand", args)


def inv_get_movements(caller: Caller, item: str | None = None, date_from: date | None = None,
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
    return _run(caller, "inv_movement_daily", sql, params, "inv_get_movements", args)


# ── PO / PR (phase 2) ────────────────────────────────────────────────────────

def po_get_outstanding(caller: Caller, supplier: str | None = None, item: str | None = None,
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
    return _run(caller, "po_outstanding", sql, params, "po_get_outstanding", args)


def po_get_match_status(caller: Caller, po_number: str | None = None, supplier: str | None = None,
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
    return _run(caller, "po_receipt_vs_invoice", sql, params, "po_get_match_status", args)


def pr_get_pending(caller: Caller, person: str | None = None, item: str | None = None,
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
    return _run(caller, "pr_pending", sql, params, "pr_get_pending", args)


def inv_get_valuation(caller: Caller, item: str | None = None, item_category=None,
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
    return _run(caller, "inv_valuation", sql, params, "inv_get_valuation", args)


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


def ar_get_aging(caller: Caller, customer: str | None = None, min_days_overdue: int | None = None,
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
    return _run(caller, "ar_aging", sql, params, "ar_get_aging", args)


def ar_get_open_invoices(caller: Caller, customer: str | None = None, invoice_num: str | None = None,
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
    return _run(caller, "ar_aging", sql, params, "ar_get_open_invoices", args)


def ar_get_receipts(caller: Caller, customer: str | None = None, receipt_number: str | None = None,
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
    return _run(caller, "ar_receipt", sql, params, "ar_get_receipts", args)


def so_get_backlog(caller: Caller, customer: str | None = None, item: str | None = None,
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
    return _run(caller, "so_backlog", sql, params, "so_get_backlog", args)


def so_get_shipment_status(caller: Caller, order_number: str | None = None, customer: str | None = None,
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
    return _run(caller, "so_shipment_status", sql, params, "so_get_shipment_status", args)


def sales_get_summary(caller: Caller, customer: str | None = None, item: str | None = None,
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
    return _run(caller, "sales_by_customer_item_month", sql, params, "sales_get_summary", args)


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


def opm_get_batch(caller: Caller, batch_no: str | None = None, product: str | None = None,
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
    return _run(caller, "batch_status", sql, params, "opm_get_batch", args)


def opm_get_yield(caller: Caller, product: str | None = None, batch_no: str | None = None,
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
    return _run(caller, "batch_yield_variance", sql, params, "opm_get_yield", args)


def opm_get_material_usage(caller: Caller, batch_no: str | None = None, ingredient: str | None = None,
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
    return _run(caller, "batch_material_usage", sql, params, "opm_get_material_usage", args)


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


# The chart of accounts is in English (611311 ELECTRICITY); people ask in
# Indonesian ("biaya listrik"). A search term that is one of these words is
# searched by its English stem instead.
_ACCOUNT_TERMS = {
    "listrik": "ELECTRIC", "air": "WATER", "gaji": "SALAR", "upah": "WAGE", "sewa": "RENT", "penyusutan": "DEPRECIATION",
    "depresiasi": "DEPRECIATION", "amortisasi": "AMORTI", "bunga": "INTEREST", "pajak": "TAX", "telepon": "TELEPHONE",
    "perjalanan": "TRAVEL", "dinas": "TRAVEL", "bensin": "FUEL", "bbm": "FUEL", "iklan": "ADVERTIS", "promosi": "PROMOTION",
    "asuransi": "INSURANCE", "perbaikan": "REPAIR", "pemeliharaan": "MAINTENANCE", "konsultan": "CONSULT",
    "pelatihan": "TRAINING", "rekrutmen": "RECRUIT", "kurs": "EXCHANGE", "selisih kurs": "EXCHANGE", "penjualan": "SALES",
    "piutang": "RECEIVABLE", "hutang": "PAYABLE", "utang": "PAYABLE", "persediaan": "INVENTOR", "kas": "CASH",
    "bank": "BANK", "sumbangan": "DONATION", "entertain": "ENTERTAIN", "jamuan": "ENTERTAIN", "pengiriman": "FREIGHT",
    "ongkos kirim": "FREIGHT", "listrik dan air": "UTILIT", "utilitas": "UTILIT", "lisensi": "LICENSE",
    "riset": "RESEARCH", "penelitian": "RESEARCH", "alat tulis": "STATIONER", "kebersihan": "CLEANING",
    "keamanan": "SECURITY", "tunjangan": "ALLOWANCE", "bonus": "BONUS", "lembur": "OVERTIME", "pesangon": "SEVERANCE",
}


# Department names in the COA (segment3) are spelled out; people use the
# usual abbreviations or Indonesian names. A term that is one of these keys is
# searched by the COA spelling instead.
_DEPT_TERMS = {
    "hrga": "HUMAN RESOURCE", "hr": "HUMAN RESOURCE", "sdm": "HUMAN RESOURCE", "personalia": "HUMAN RESOURCE",
    "ga": "GENERAL AFFAIR", "umum": "GENERAL AFFAIR", "qa": "QUALITY ASSURANCE", "qc": "QUALITY CONTROL",
    "ppic": "PRODUCTION PLANNING", "gudang": "WAREHOUSE", "produksi": "PRODUCTION", "pajak": "TAX",
    "akuntansi": "ACCOUNTING", "finance": "ACCOUNTING", "keuangan": "ACCOUNTING", "fa": "ACCOUNTING",
    "pembelian": "PURCHASING", "sm": "SALES MARKETING", "penjualan": "SALES", "pemasaran": "MARKETING",
    "ra": "REGULATORY AFFAIR", "regulatory": "REGULATORY AFFAIR", "bd": "BUSINESS DEVELOPMENT",
    "sd": "STRATEGY DEVELOPMENT", "direksi": "DIRECTOR", "teknik": "ENGINEERING", "validasi": "VALIDATION",
    "hbc": "HEALTH BEAUTY COSMETIC", "ma": "MEDICAL AFFAIR", "medical": "MEDICAL AFFAIR",
}


def _dept_term(text):
    """Department abbreviation / Indonesian name -> the COA spelling; else as given."""
    t = _val(text)
    if not isinstance(t, str):
        return t
    key = t.strip().lower()
    for prefix in ("departemen ", "department ", "dept ", "divisi "):
        if key.startswith(prefix):
            key = key[len(prefix):]
    return _DEPT_TERMS.get(key, t)


def _account_term(text):
    """Indonesian account word -> the English stem the COA uses; else as given."""
    t = _val(text)
    if not isinstance(t, str):
        return t
    key = t.strip().lower()
    for prefix in ("biaya ", "beban ", "akun "):
        if key.startswith(prefix):
            key = key[len(prefix):]
    return _ACCOUNT_TERMS.get(key, t)


_ACCOUNT_FILTER = """(%(acc)s::text IS NULL OR account_code LIKE %(acc)s::text || '%%'
                      OR account_desc ILIKE '%%' || %(acc)s::text || '%%')"""
_DEPT_FILTER = """(%(dept)s::text IS NULL OR dept_code = %(dept)s::text OR dept_desc ILIKE '%%' || %(dept)s::text || '%%')"""


def gl_get_pl(caller: Caller, period: str, ytd: bool = False, department: str | None = None,
           compare_prior_year: bool = False, level: str = "line") -> dict:
    """Profit & loss in the Financial Statement report's layout: lines by
    section with a 'TOTAL <section>' row after each, then the report's
    subtotals (net sales, gross profit, profit
    before / after tax, total comprehensive income). compare_prior_year
    adds the same period one year earlier."""
    args = {"period": period, "ytd": ytd, "department": department, "compare_prior_year": compare_prior_year,
            "level": level}
    cond, params = _gl_period_filter(period, ytd)
    params.update({"dept": _dept_term(department)})
    prior_cond = "FALSE"
    if compare_prior_year and "py" in params:
        prior_cond = cond.replace("%(py)s", "(%(py)s - 1)")
    grp = "section, section_order" if level == "section" else "section, section_order, line, line_order"
    sel = "section" if level == "section" else "section, line"
    # With a comparison the tool also returns the difference, for the same
    # reason: models round it when they subtract themselves.
    diff = ""
    if prior_cond != "FALSE":
        diff = (", amount_idr - amount_prior_year_idr AS selisih_idr, ROUND(100.0 * (amount_idr - amount_prior_year_idr)"
                " / NULLIF(ABS(amount_prior_year_idr), 0), 1) AS perubahan_pct")
    # At line level each section's total follows its lines, so the model reads
    # the subtotal instead of adding lines itself (Haiku got operating
    # expenses wrong by Rp 1,3 M doing exactly that).
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
        ), rpt AS (
        SELECT {'section' if level == 'section' else 'section, line'}, amount_idr, amount_prior_year_idr, so, lo
          FROM lines
        {'' if level == 'section' else '''
        UNION ALL SELECT section, 'TOTAL ' || section, SUM(amount_idr), SUM(amount_prior_year_idr), MIN(so), 999
          FROM lines GROUP BY section'''}
        UNION ALL SELECT {"'NET SALES'" if level == 'section' else "'TOTAL', 'NET SALES'"}, sales, p_sales, 10, 1 FROM tot
        UNION ALL SELECT {"'GROSS PROFIT'" if level == 'section' else "'TOTAL', 'GROSS PROFIT'"}, sales - cogs, p_sales - p_cogs, 10, 2 FROM tot
        UNION ALL SELECT {"'PROFIT BEFORE TAX'" if level == 'section' else "'TOTAL', 'PROFIT BEFORE TAX'"}, sales - cogs - opex + other,
                         p_sales - p_cogs - p_opex + p_other, 10, 3 FROM tot
        UNION ALL SELECT {"'PROFIT AFTER TAX'" if level == 'section' else "'TOTAL', 'PROFIT AFTER TAX'"}, sales - cogs - opex + other + tax,
                         p_sales - p_cogs - p_opex + p_other + p_tax, 10, 4 FROM tot
        UNION ALL SELECT {"'TOTAL COMPREHENSIVE INCOME'" if level == 'section' else "'TOTAL', 'TOTAL COMPREHENSIVE INCOME'"},
                         sales - cogs - opex + other + tax + oci, p_sales - p_cogs - p_opex + p_other + p_tax + p_oci, 10, 5 FROM tot
        UNION ALL SELECT {"'UNMAPPED'" if level == 'section' else "'UNMAPPED', 'AKUN BELUM TERPETAKAN (tidak masuk total)'"},
                         unmapped, NULL, 11, 1 FROM tot WHERE unmapped <> 0
        )
        SELECT *{diff} FROM rpt ORDER BY so, lo
    """
    return _run(caller, "pl_monthly", sql, params, "gl_get_pl", args)


def gl_get_trial_balance(caller: Caller, period: str, account: str | None = None, department: str | None = None,
                      statement: str | None = None, group_by: str = "account") -> dict:
    """Trial balance for one period (month or MON-YY). Balances in GL's
    debit-positive convention (begin, dr, cr, end) plus end_balance_fs in the
    statement's reading (liabilities/equity positive)."""
    args = {"period": period, "account": account, "department": department, "statement": statement,
            "group_by": group_by}
    cond, params = _gl_period_filter(period)
    if "pn" not in params:
        raise sql_guard.SqlRejected("Trial balance butuh satu periode bulan (YYYY-MM atau JUL-26), bukan setahun.")
    params.update({"acc": _account_term(account), "dept": _dept_term(department), "st": _val(statement)})
    where = f"""
         WHERE {cond}
           AND {_ACCOUNT_FILTER}
           AND {_DEPT_FILTER}
           AND (%(st)s::text IS NULL OR statement = UPPER(%(st)s::text))
    """
    measures = """SUM(begin_balance) AS begin_balance, SUM(period_dr) AS period_dr, SUM(period_cr) AS period_cr,
                  SUM(end_balance) AS end_balance, SUM(end_balance_fs) AS end_balance_fs"""
    marts = ["gl_trial_balance"]
    if group_by == "fs_line" and not account and not department and statement in (None, "", "BS", "bs"):
        # Current-year retained earnings and OCI are not in the GL until the
        # year is closed. The Financial Statement report fills them with the
        # year-to-date P&L (get_balance_sheet); doing the same here makes the
        # two balance sheets agree line for line (verified at SEP-26).
        marts.append("pl_monthly")
        sql = f"""
            WITH tb AS (
                SELECT statement, section, section_order, fs_line, line_order, {measures}
                  FROM mart.gl_trial_balance {where}
                 GROUP BY statement, section, section_order, fs_line, line_order
            ), pl AS (
                SELECT COALESCE(SUM(amount) FILTER (WHERE section IN ('SALES', 'OTHER INCOME/EXPENSE', 'TAX')), 0)
                     - COALESCE(SUM(amount) FILTER (WHERE section IN ('COGS', 'OPERATING EXPENSES')), 0) AS pat,
                       COALESCE(SUM(amount) FILTER (WHERE section = 'OTHER COMPREHENSIVE INCOME'), 0) AS oci
                  FROM mart.pl_monthly
                 WHERE period_year = %(py)s AND period_num <= %(pn)s AND NOT is_adjustment
            )
            SELECT statement, section, fs_line, begin_balance, period_dr, period_cr, end_balance, end_balance_fs
              FROM (
                SELECT * FROM tb
                 WHERE fs_line NOT IN ('RETAINED EARNINGS - CURRENT YEAR', 'OTHER COMPREHENSIVE INCOME - CURRENT YEAR')
                UNION ALL
                SELECT 'BS', 'EQUITY', 5, 'RETAINED EARNINGS - CURRENT YEAR', 3, NULL, NULL, NULL, NULL, pat FROM pl
                UNION ALL
                SELECT 'BS', 'EQUITY', 5, 'OTHER COMPREHENSIVE INCOME - CURRENT YEAR', 5, NULL, NULL, NULL, NULL, oci FROM pl
              ) x
             ORDER BY statement, section_order, line_order
        """
    elif group_by == "fs_line":
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
    return _run(caller, marts, sql, params, "gl_get_trial_balance", args)


def gl_get_journals(caller: Caller, period: str | None = None, date_from: date | None = None,
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
    params.update({"df": date_from, "dt": date_to, "acc": _account_term(account), "dept": _dept_term(department),
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
    return _run(caller, "gl_journal_detail", sql, params, "gl_get_journals", args)


# ── Finance close, Cash Management, Fixed Assets (library v2 12-13) ─────────

def _period_name(period: str | None) -> str | None:
    """'AUG-26', '2026-08' or 'Aug 2026' -> 'AUG-26' (CKDO_GL_CAL names)."""
    import re as _re
    if not period or not str(period).strip():
        return None
    p = str(period).strip().upper()
    if _re.match(r"^[A-Z]{3}-\d{2}$", p) and p[:3] in _MON:
        return p
    m = _re.match(r"^(\d{4})-(\d{1,2})$", p)
    if m and 1 <= int(m.group(2)) <= 12:
        return f"{_MON[int(m.group(2)) - 1]}-{m.group(1)[2:]}"
    m = _re.match(r"^([A-Z]{3})[A-Z]*\s+(\d{4})$", p)
    if m and m.group(1) in _MON:
        return f"{m.group(1)}-{m.group(2)[2:]}"
    raise sql_guard.SqlRejected(f"Format periode '{period}' tidak dikenal — pakai AUG-26 atau 2026-08.")


def gl_get_period_status(caller: Caller, period: str | None = None, application: str | None = None) -> dict:
    """Status of a period in every application (GL, AP, AR, PO, INV, OPM
    costing, FA with depreciation run). Without a period: the current month
    and the two before it."""
    args = {"period": period, "application": application}
    sql = """
        SELECT period_name, application, book_type_code, status, deprn_run, start_date, end_date, last_update_date
          FROM mart.gl_period_status
         WHERE ((%(p)s::text IS NULL AND start_date BETWEEN (now() AT TIME ZONE 'Asia/Jakarta')::date - 70
                                                        AND (now() AT TIME ZONE 'Asia/Jakarta')::date)
                OR period_name = %(p)s::text)
           AND (%(a)s::text IS NULL OR application = UPPER(%(a)s::text))
         ORDER BY start_date DESC, application_order, book_type_code
    """
    return _run(caller, "gl_period_status", sql, {"p": _period_name(period), "a": _val(application)},
                "gl_get_period_status", args)


def gl_get_subledger_gap(caller: Caller, period: str | None = None, application: str | None = None,
                         group_by: str = "summary") -> dict:
    """What keeps a subledger from agreeing with GL: events not accounted or
    in error, entries still draft or final but not transferred, and GL
    journals not posted. summary = count, amount and oldest per kind ×
    application × period; detail = the documents."""
    args = {"period": period, "application": application, "group_by": group_by}
    where = """
         WHERE (%(p)s::text IS NULL OR period_name = %(p)s::text)
           AND (%(a)s::text IS NULL OR application ILIKE %(a)s::text)
    """
    if group_by == "detail":
        sql = f"""
            SELECT application, kind_desc, period_name, txn_date, age_days, event_type, entity_code,
                   transaction_number, amount_idr, detail
              FROM mart.sla_gl_gap {where}
             ORDER BY age_days DESC
        """
    else:
        sql = f"""
            SELECT application, kind_desc, period_name, COUNT(*) AS jumlah, SUM(amount_idr) AS amount_idr,
                   MIN(txn_date) AS tertua, (ARRAY_AGG(transaction_number ORDER BY txn_date))[1:5] AS contoh
              FROM mart.sla_gl_gap {where}
             GROUP BY application, kind_desc, period_name
             ORDER BY period_name, application, kind_desc
        """
    return _run(caller, "sla_gl_gap", sql, {"p": _period_name(period), "a": _val(application)},
                "gl_get_subledger_gap", args)


def po_get_uninvoiced_receipts(caller: Caller, as_of_period: str | None = None, supplier: str | None = None,
                               group_by: str = "supplier") -> dict:
    """Received-not-billed PO distributions (the accrual base) as of now.
    as_of_period limits to POs dated up to the end of that period — the mart
    holds today's received and billed quantities, not a history of them."""
    args = {"as_of_period": as_of_period, "supplier": supplier, "group_by": group_by}
    end = None
    pn = _period_name(as_of_period)
    if pn:
        import calendar
        y, m = 2000 + int(pn[4:]), _MON.index(pn[:3]) + 1
        end = date(y, m, calendar.monthrange(y, m)[1])
    where = """
         WHERE qty_received_not_billed > 0
           AND COALESCE(closed_code, 'OPEN') NOT IN ('CLOSED', 'FINALLY CLOSED', 'CLOSED FOR INVOICE')
           AND (%(end)s::date IS NULL OR po_date <= %(end)s::date)
           AND (%(s)s::text IS NULL OR vendor_name ILIKE %(s)s::text)
    """
    if group_by == "po":
        sql = f"""
            SELECT po_number, vendor_name, item_code, item_desc, uom, qty_received_not_billed,
                   amount_received_not_billed_idr, po_date, match_type
              FROM mart.po_receipt_vs_invoice {where}
             ORDER BY amount_received_not_billed_idr DESC
        """
    else:
        sql = f"""
            SELECT vendor_name, COUNT(DISTINCT po_number) AS jml_po, COUNT(*) AS jml_baris,
                   SUM(amount_received_not_billed_idr) AS amount_received_not_billed_idr, MIN(po_date) AS po_tertua
              FROM mart.po_receipt_vs_invoice {where}
             GROUP BY vendor_name ORDER BY amount_received_not_billed_idr DESC
        """
    return _run(caller, "po_receipt_vs_invoice", sql, {"end": end, "s": _like(supplier)},
                "po_get_uninvoiced_receipts", args)


def so_get_shipped_not_invoiced(caller: Caller, date_from: date | None = None, customer: str | None = None) -> dict:
    args = {"date_from": date_from, "customer": customer}
    sql = """
        SELECT order_number, line_number, business_type, customer_name, item_code, item_desc, uom, shipped_qty,
               actual_shipment_date, days_since_ship, currency_code, amount_idr, line_status, autoinvoice_errors
          FROM mart.so_shipped_not_invoiced
         WHERE (%(df)s::date IS NULL OR actual_shipment_date >= %(df)s::date)
           AND (%(c)s::text IS NULL OR customer_name ILIKE %(c)s::text)
         ORDER BY actual_shipment_date
    """
    return _run(caller, "so_shipped_not_invoiced", sql, {"df": date_from, "c": _like(customer)},
                "so_get_shipped_not_invoiced", args)


def ar_get_unapplied_receipts(caller: Caller, customer: str | None = None) -> dict:
    """Customer receipts (or parts of them) not applied to an invoice:
    unapplied and on-account amounts."""
    args = {"customer": customer}
    sql = """
        SELECT customer_name, receipt_number, receipt_date, receipt_method, currency_code,
               SUM(amount_entered) AS amount_entered, SUM(amount_idr) AS amount_idr,
               STRING_AGG(DISTINCT application_status_desc, '; ') AS status
          FROM mart.ar_receipt
         WHERE application_status IN ('UNAPP', 'ONACC')
           AND NOT is_reversed
           AND (%(c)s::text IS NULL OR customer_name ILIKE %(c)s::text)
         GROUP BY customer_name, receipt_number, receipt_date, receipt_method, currency_code
        HAVING ABS(SUM(amount_idr)) >= 1
         ORDER BY receipt_date
    """
    return _run(caller, "ar_receipt", sql, {"c": _like(customer)}, "ar_get_unapplied_receipts", args)


def ar_get_autoinvoice_errors(caller: Caller, date_from: date | None = None, so_number: str | None = None,
                              group_by: str = "none") -> dict:
    args = {"date_from": date_from, "so_number": so_number, "group_by": group_by}
    where = """
         WHERE (%(df)s::date IS NULL OR created_date >= %(df)s::date)
           AND (%(so)s::text IS NULL OR so_number = %(so)s::text)
    """
    if group_by == "error":
        sql = f"""
            SELECT status, error_message, COUNT(DISTINCT interface_line_id) AS jml_baris,
                   COUNT(DISTINCT so_number) AS jml_so, SUM(amount_idr) AS amount_idr, MIN(created_date) AS tertua
              FROM mart.ar_autoinvoice_error {where}
             GROUP BY status, error_message ORDER BY jml_baris DESC
        """
    else:
        sql = f"""
            SELECT so_number, customer_name, batch_source_name, status, error_message, invalid_value, trx_date,
                   gl_date, currency_code, amount, amount_idr, age_days
              FROM mart.ar_autoinvoice_error {where}
             ORDER BY created_date
        """
    return _run(caller, "ar_autoinvoice_error", sql, {"df": date_from, "so": _val(so_number)},
                "ar_get_autoinvoice_errors", args)


def opm_get_open_batches(caller: Caller, status: str | None = None, days_open: int | None = None) -> dict:
    """Batches not yet Closed (Pending, WIP, Completed), with how long they
    have been open since actual — or planned — start."""
    args = {"status": status, "days_open": days_open}
    sql = """
        SELECT batch_no, batch_status_desc AS status, product_code, product_desc, plan_start_date,
               actual_start_date, actual_cmplt_date,
               (now() AT TIME ZONE 'Asia/Jakarta')::date - COALESCE(actual_start_date, plan_start_date)::date AS days_open,
               product_plan_qty, product_actual_qty, product_uom
          FROM mart.batch_status
         WHERE batch_status_desc IN ('Pending', 'WIP', 'Completed')
           AND (%(s)s::text IS NULL OR batch_status_desc ILIKE %(s)s::text)
           AND (%(d)s::int IS NULL
                OR (now() AT TIME ZONE 'Asia/Jakarta')::date - COALESCE(actual_start_date, plan_start_date)::date >= %(d)s::int)
         ORDER BY days_open DESC NULLS LAST
    """
    return _run(caller, "batch_status", sql, {"s": _val(status), "d": days_open}, "opm_get_open_batches", args)


def ce_get_unreconciled(caller: Caller, bank_account_name: str | None = None, date_to: date | None = None,
                        side: str | None = None, group_by: str = "summary") -> dict:
    """Unreconciled bank items: statement lines with no system match (BANK),
    and AP payments / AR receipts / bank transfers not yet on a statement
    (SYSTEM). The summary shows each account's last statement date — when
    statements stop being loaded, everything after looks unreconciled."""
    args = {"bank_account_name": bank_account_name, "date_to": date_to, "side": side, "group_by": group_by}
    where = """
         WHERE (%(b)s::text IS NULL OR bank_account_name ILIKE %(b)s::text OR bank_name ILIKE %(b)s::text)
           AND (%(dt)s::date IS NULL OR trx_date <= %(dt)s::date)
           AND (%(sd)s::text IS NULL OR side = UPPER(%(sd)s::text))
    """
    if group_by == "detail":
        sql = f"""
            SELECT bank_account_name, side_desc, source, doc_number, trx_date, age_days, currency_code,
                   amount_entered, amount_idr, status, description, statement_number
              FROM mart.ce_unreconciled {where}
             ORDER BY bank_account_name, trx_date
        """
    else:
        sql = f"""
            SELECT bank_account_name, side_desc, source, COUNT(*) AS jumlah, SUM(amount_idr) AS amount_idr,
                   MIN(trx_date) AS tertua, MAX(last_statement_date) AS statement_terakhir
              FROM mart.ce_unreconciled {where}
             GROUP BY bank_account_name, side_desc, source
             ORDER BY bank_account_name, side_desc, source
        """
    return _run(caller, "ce_unreconciled", sql,
                {"b": _like(bank_account_name), "dt": date_to, "sd": _val(side)}, "ce_get_unreconciled", args)


def fa_get_assets(caller: Caller, category: str | None = None, location: str | None = None,
                  asset: str | None = None, status: str | None = None, group_by: str = "category") -> dict:
    args = {"category": category, "location": location, "asset": asset, "status": status, "group_by": group_by}
    where = """
         WHERE (%(c)s::text IS NULL OR category ILIKE %(c)s::text OR category_desc ILIKE %(c)s::text)
           AND (%(l)s::text IS NULL OR location ILIKE %(l)s::text)
           AND (%(a)s::text IS NULL OR asset_number = %(av)s::text OR description ILIKE %(a)s::text
                OR tag_number = %(av)s::text)
           AND (%(st)s::text IS NULL OR asset_status ILIKE %(st)s::text)
    """
    if group_by == "asset":
        sql = f"""
            SELECT asset_number, description, category, location, date_placed_in_service, asset_status, cost,
                   accumulated_depreciation, nbv, ytd_deprn, last_deprn_period, life_in_months, tag_number
              FROM mart.fa_asset_register {where}
             ORDER BY category, asset_number
        """
    else:
        dim = {"location": "location", "status": "asset_status"}.get(group_by, "category, category_desc")
        sql = f"""
            SELECT {dim}, COUNT(*) AS jml_aset, SUM(cost) AS cost, SUM(accumulated_depreciation) AS akumulasi_penyusutan,
                   SUM(nbv) AS nbv, SUM(ytd_deprn) AS penyusutan_ytd
              FROM mart.fa_asset_register {where}
             GROUP BY {dim} ORDER BY cost DESC
        """
    return _run(caller, "fa_asset_register", sql,
                {"c": _like(category), "l": _like(location), "a": _like(asset), "av": _val(asset),
                 "st": _like(status)}, "fa_get_assets", args)


def fa_get_depreciation(caller: Caller, period: str, category: str | None = None, group_by: str = "category") -> dict:
    args = {"period": period, "category": category, "group_by": group_by}
    where = """
         WHERE period_name = %(p)s::text
           AND (%(c)s::text IS NULL OR category ILIKE %(c)s::text OR category_desc ILIKE %(c)s::text)
    """
    if group_by == "asset":
        sql = f"""
            SELECT asset_number, description, category, location, deprn_amount, ytd_deprn, deprn_reserve
              FROM mart.fa_depreciation {where}
             ORDER BY deprn_amount DESC
        """
    else:
        sql = f"""
            SELECT category, category_desc, COUNT(*) AS jml_aset, SUM(deprn_amount) AS penyusutan_periode,
                   SUM(ytd_deprn) AS penyusutan_ytd, SUM(deprn_reserve) AS akumulasi
              FROM mart.fa_depreciation {where}
             GROUP BY category, category_desc ORDER BY penyusutan_periode DESC
        """
    return _run(caller, "fa_depreciation", sql, {"p": _period_name(period), "c": _like(category)},
                "fa_get_depreciation", args)


# ── Rest of the library v2 catalog (ext_sql.py) ─────────────────────────────

def _month_range(period: str | None):
    """(first day, last day) of a period given as AUG-26 / 2026-08."""
    import calendar
    pn = _period_name(period)
    if not pn:
        return None, None
    y, m = 2000 + int(pn[4:]), _MON.index(pn[:3]) + 1
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def lookup_master(caller: Caller, text: str, type: str | None = None) -> dict:
    """Codes for a partial name (or names for a code): item, supplier,
    customer, account, department. An exact code match comes first."""
    args = {"text": text, "type": type}
    sql = """
        SELECT type, code, name, extra
          FROM mart.master_lookup
         WHERE (%(t)s::text IS NULL OR type = LOWER(%(t)s::text))
           AND (UPPER(code) = UPPER(%(x)s::text) OR name ILIKE %(xl)s::text OR code ILIKE %(xl)s::text)
         ORDER BY (UPPER(code) = UPPER(%(x)s::text)) DESC, type, name
    """
    if type == "account":
        term = _account_term(text)
    elif type == "department":
        term = _dept_term(text)
    elif type is None:
        term = _dept_term(text) if _dept_term(text) != _val(text) else _account_term(text)
    else:
        term = _val(text)
    return _run(caller, "master_lookup", sql, {"t": _val(type), "x": _val(text), "xl": _like(term)},
                "lookup_master", args)


def po_get_document(caller: Caller, po_number: str) -> dict:
    """One PO, open or closed: every shipment with ordered, received, billed
    and cancelled quantities, and the invoices matched to it — plus the
    Purchase History report's columns (payment term, PR/requestor, latest
    receipt, category, material type, country of origin, org)."""
    args = {"po_number": po_number}
    sql = """
        SELECT s.po_number, s.po_type, s.po_status, s.po_date, s.approved_date, s.vendor_name, s.buyer_name,
               s.payment_term, s.pr_number, s.requestor, s.organization_name,
               s.line_num, s.shipment_num, s.item_code, s.item_desc, s.item_category, s.material_type,
               s.country_of_origin, s.uom, s.qty_ordered, s.qty_received, s.qty_billed, s.qty_cancelled,
               s.qty_outstanding, s.receipt_number, s.receipt_date, s.currency_code, s.unit_price_entered,
               s.amount_entered, s.amount_idr, s.need_by_date, s.promised_date, s.closed_code, i.invoices
          FROM mart.po_shipment s
          LEFT JOIN (SELECT line_location_id, STRING_AGG(DISTINCT last_invoice_num, ', ') AS invoices
                       FROM mart.po_receipt_vs_invoice GROUP BY line_location_id) i
                 ON i.line_location_id = s.line_location_id
         WHERE UPPER(s.po_number) = UPPER(%(po)s::text)
         ORDER BY s.release_num NULLS FIRST, s.line_num, s.shipment_num
    """
    return _run(caller, ["po_shipment", "po_receipt_vs_invoice"], sql, {"po": _val(po_number)},
                "po_get_document", args)


def po_get_pending_approval(caller: Caller, min_days: int | None = None, doc_type: str | None = None,
                            approver: str | None = None, include_incomplete: bool = False) -> dict:
    """Documents submitted and waiting for an approver (In Process,
    Pre-Approved, Requires Reapproval). Incomplete = a draft never submitted —
    hundreds of them sit since 2019 — only with include_incomplete."""
    args = {"min_days": min_days, "doc_type": doc_type, "approver": approver, "include_incomplete": include_incomplete}
    sql = """
        SELECT doc_type, doc_number, authorization_status, pending_approver, preparer, days_waiting, submitted_date,
               last_action, vendor_name, currency_code, amount_entered, amount_idr, description
          FROM mart.po_approval_pending
         WHERE (%(d)s::int IS NULL OR days_waiting >= %(d)s::int)
           AND (%(inc)s OR authorization_status <> 'INCOMPLETE')
           AND (%(t)s::text IS NULL OR doc_type = UPPER(%(t)s::text))
           AND (%(a)s::text IS NULL OR pending_approver ILIKE %(a)s::text)
         ORDER BY days_waiting DESC
    """
    return _run(caller, "po_approval_pending", sql, {"d": min_days, "t": _val(doc_type), "a": _like(approver),
                                                     "inc": include_incomplete},
                "po_get_pending_approval", args)


def ap_get_invoice(caller: Caller, invoice_num: str, supplier: str | None = None) -> dict:
    """One supplier invoice, paid or not: amounts, payment status, next due
    date, payments made and holds still active."""
    args = {"invoice_num": invoice_num, "supplier": supplier}
    sql = """
        SELECT invoice_num, vendor_name, invoice_type, invoice_date, gl_date, currency_code, invoice_amount_entered,
               invoice_amount_idr, payment_status, amount_remaining_entered, amount_remaining_idr, next_due_date,
               days_overdue, payment_count, paid_amount_idr, last_payment_date, payment_numbers, active_holds,
               hold_codes, cancelled_date, description
          FROM mart.ap_invoice
         WHERE UPPER(invoice_num) = UPPER(%(i)s::text)
           AND (%(s)s::text IS NULL OR vendor_name ILIKE %(s)s::text)
         ORDER BY invoice_date DESC
    """
    return _run(caller, "ap_invoice", sql, {"i": _val(invoice_num), "s": _like(supplier)}, "ap_get_invoice", args)


def ap_get_due_forecast(caller: Caller, weeks_ahead: int = 8, supplier: str | None = None) -> dict:
    """Cash needed for supplier invoices falling due, per week (Monday
    start), with everything already overdue in one row at the top."""
    weeks_ahead = max(1, min(int(weeks_ahead or 8), 52))
    args = {"weeks_ahead": weeks_ahead, "supplier": supplier}
    sql = """
        WITH t AS (SELECT (now() AT TIME ZONE 'Asia/Jakarta')::date AS d)
        SELECT CASE WHEN o.due_date < t.d THEN 'Sudah lewat jatuh tempo'
                    ELSE 'Minggu mulai ' || TO_CHAR(DATE_TRUNC('week', o.due_date), 'DD-Mon-YYYY') END AS periode,
               MIN(CASE WHEN o.due_date < t.d THEN DATE '1900-01-01' ELSE DATE_TRUNC('week', o.due_date)::date END) AS urut,
               COUNT(*) AS jml_invoice, COUNT(DISTINCT o.vendor_name) AS jml_supplier,
               SUM(o.amount_remaining_idr) AS amount_idr
          FROM mart.ap_open_invoice o, t
         WHERE o.due_date <= t.d + %(w)s::int * 7
           AND (%(s)s::text IS NULL OR o.vendor_name ILIKE %(s)s::text)
         GROUP BY 1 ORDER BY urut
    """
    return _run(caller, "ap_open_invoice", sql, {"w": weeks_ahead, "s": _like(supplier)}, "ap_get_due_forecast", args)


def ap_get_withholding(caller: Caller, period: str | None = None, tax_code: str | None = None,
                       supplier: str | None = None, group_by: str = "tax") -> dict:
    """Withholding tax (PPh) deducted from supplier invoices, 24 months."""
    args = {"period": period, "tax_code": tax_code, "supplier": supplier, "group_by": group_by}
    where = """
         WHERE (%(p)s::text IS NULL OR period_name = %(p)s::text)
           AND (%(t)s::text IS NULL OR tax_name ILIKE %(t)s::text)
           AND (%(s)s::text IS NULL OR vendor_name ILIKE %(s)s::text)
    """
    if group_by == "invoice":
        sql = f"""
            SELECT period_name, vendor_name, invoice_num, invoice_date, tax_name, tax_rate, amount_idr, account_code
              FROM mart.ap_withholding {where} ORDER BY accounting_date, vendor_name
        """
    else:
        dim = "vendor_name" if group_by == "supplier" else "tax_name, tax_rate"
        sql = f"""
            SELECT {dim}, COUNT(DISTINCT invoice_id) AS jml_invoice, SUM(amount_idr) AS amount_idr
              FROM mart.ap_withholding {where} GROUP BY {dim} ORDER BY amount_idr DESC
        """
    return _run(caller, "ap_withholding", sql, {"p": _period_name(period), "t": _like(tax_code), "s": _like(supplier)},
                "ap_get_withholding", args)


def so_get_order(caller: Caller, order_number: str) -> dict:
    """One sales order, open or closed: each line with ordered, shipped and
    invoiced quantities, delivery, lot and AR invoice numbers."""
    args = {"order_number": order_number}
    sql = """
        SELECT order_number, order_type, ordered_date, header_status, customer_name, line_number, shipment_number,
               item_code, item_desc, uom, ordered_qty, shipped_qty, invoiced_qty, cancelled_qty, line_status,
               currency_code, unit_selling_price, amount_ordered_idr, schedule_ship_date, actual_shipment_date,
               delivery_names, lot_numbers, invoice_numbers
          FROM mart.so_order_line
         WHERE order_number = %(o)s::text
         ORDER BY line_number, shipment_number
    """
    return _run(caller, "so_order_line", sql, {"o": _val(order_number)}, "so_get_order", args)


def so_get_holds(caller: Caller, hold_name: str | None = None, customer: str | None = None) -> dict:
    args = {"hold_name": hold_name, "customer": customer}
    sql = """
        SELECT order_number, order_type, customer_name, hold_name, hold_type, hold_level, line_number, applied_date,
               days_on_hold, hold_until_date, applied_by, hold_comment, order_amount_idr
          FROM mart.so_hold
         WHERE (%(h)s::text IS NULL OR hold_name ILIKE %(h)s::text)
           AND (%(c)s::text IS NULL OR customer_name ILIKE %(c)s::text)
         ORDER BY days_on_hold DESC
    """
    return _run(caller, "so_hold", sql, {"h": _like(hold_name), "c": _like(customer)}, "so_get_holds", args)


def ar_get_customer_balance(caller: Caller, customer: str) -> dict:
    """A customer's open receivable by currency (total, overdue, oldest due
    date) and — for callers who may read receipts — unapplied cash."""
    args = {"customer": customer}
    with_unapplied = caller.can_read("ar_receipt")
    unapplied = """
        , u AS (SELECT customer_name, SUM(amount_idr) AS unapplied_idr FROM mart.ar_receipt
                 WHERE application_status IN ('UNAPP', 'ONACC') AND NOT is_reversed
                   AND customer_name ILIKE %(c)s::text GROUP BY customer_name)""" if with_unapplied else ""
    sql = f"""
        WITH a AS (
            SELECT customer_num, customer_name, currency_code, COUNT(*) AS jml_dokumen,
                   SUM(amount_remaining_entered) AS sisa_entered, SUM(amount_remaining_idr) AS sisa_idr,
                   SUM(amount_remaining_idr) FILTER (WHERE days_overdue > 0) AS overdue_idr,
                   MIN(due_date) AS jatuh_tempo_tertua, MAX(days_overdue) AS overdue_terlama_hari
              FROM mart.ar_aging WHERE customer_name ILIKE %(c)s::text
             GROUP BY customer_num, customer_name, currency_code
        ){unapplied}
        SELECT a.*{", u.unapplied_idr" if with_unapplied else ""}
          FROM a {"LEFT JOIN u ON u.customer_name = a.customer_name" if with_unapplied else ""}
         ORDER BY a.sisa_idr DESC
    """
    marts = ["ar_aging"] + (["ar_receipt"] if with_unapplied else [])
    return _run(caller, marts, sql, {"c": _like(customer)}, "ar_get_customer_balance", args)


def inv_get_stock_card(caller: Caller, item: str, period: str, subinventory: str | None = None) -> dict:
    """Stock card of one item code for one month: opening balance, each day ×
    transaction type in/out with running balance, closing balance. Opening =
    today's on-hand minus every movement since the period start. Movements
    are per day and type (no lot)."""
    args = {"item": item, "period": period, "subinventory": subinventory}
    start, end = _month_range(period)
    if not start:
        raise sql_guard.SqlRejected("Periode wajib, format AUG-26 atau 2026-08.")
    sql = """
        WITH orgs AS (SELECT DISTINCT organization_code FROM mart.inv_onhand_lot),
        mv AS (
            SELECT txn_date, transaction_type, SUM(qty_in) AS qty_in, SUM(qty_out) AS qty_out, SUM(net_qty) AS net_qty,
                   MAX(uom) AS uom
              FROM mart.inv_movement_daily
             WHERE UPPER(item_code) = UPPER(%(i)s::text)
               AND organization_code IN (SELECT organization_code FROM orgs)
               AND (%(sub)s::text IS NULL OR subinventory_code = %(sub)s::text)
               AND txn_date >= %(s)s::date
             GROUP BY txn_date, transaction_type
        ), oh AS (
            SELECT COALESCE(SUM(onhand_qty), 0) AS q, MAX(uom) AS uom FROM mart.inv_onhand_lot
             WHERE UPPER(item_code) = UPPER(%(i)s::text)
               AND (%(sub)s::text IS NULL OR subinventory_code = %(sub)s::text)
        ), op AS (
            SELECT oh.q - COALESCE((SELECT SUM(net_qty) FROM mv), 0) AS opening, oh.uom FROM oh
        ), rows AS (
            SELECT txn_date, transaction_type, qty_in, qty_out,
                   (SELECT opening FROM op) + SUM(net_qty) OVER (ORDER BY txn_date, transaction_type) AS saldo
              FROM mv WHERE txn_date <= %(e)s::date
        )
        SELECT NULL::date AS tanggal, 'SALDO AWAL' AS keterangan, NULL::numeric AS masuk, NULL::numeric AS keluar,
               (SELECT opening FROM op) AS saldo, (SELECT uom FROM op) AS uom, 0 AS urut
        UNION ALL
        SELECT txn_date, transaction_type, qty_in, qty_out, saldo, (SELECT uom FROM op), 1 FROM rows
        UNION ALL
        SELECT %(e)s::date, 'SALDO AKHIR', (SELECT SUM(qty_in) FROM rows), (SELECT SUM(qty_out) FROM rows),
               (SELECT opening FROM op) + COALESCE((SELECT SUM(net_qty) FROM mv WHERE txn_date <= %(e)s::date), 0),
               (SELECT uom FROM op), 2
        ORDER BY urut, tanggal, keterangan
    """
    return _run(caller, ["inv_movement_daily", "inv_onhand_lot"], sql,
                {"i": _val(item), "s": start, "e": end, "sub": _val(subinventory)}, "inv_get_stock_card", args)


def inv_get_slow_moving(caller: Caller, days_no_movement: int = 180, subinventory_type: str | None = "GOOD") -> dict:
    """Items with stock on hand and no movement for N days (or none on
    record), with quantity and last movement date."""
    args = {"days_no_movement": days_no_movement, "subinventory_type": subinventory_type}
    sql = """
        WITH last_mv AS (
            SELECT item_code, MAX(txn_date) AS last_txn FROM mart.inv_movement_daily GROUP BY item_code
        )
        SELECT o.item_code, MAX(o.item_desc) AS item_desc, MAX(o.item_category) AS item_category, MAX(o.uom) AS uom,
               SUM(o.onhand_qty) AS onhand_qty, COUNT(DISTINCT o.lot_number) AS jml_lot, MAX(l.last_txn) AS gerak_terakhir,
               (now() AT TIME ZONE 'Asia/Jakarta')::date - MAX(l.last_txn) AS hari_diam, MIN(o.expiration_date) AS ed_terdekat
          FROM mart.inv_onhand_lot o
          LEFT JOIN last_mv l ON l.item_code = o.item_code
         WHERE o.onhand_qty > 0
           AND (%(st)s::text IS NULL OR o.subinventory_type = %(st)s::text)
         GROUP BY o.item_code
        HAVING MAX(l.last_txn) IS NULL
            OR (now() AT TIME ZONE 'Asia/Jakarta')::date - MAX(l.last_txn) >= %(d)s::int
         ORDER BY hari_diam DESC NULLS FIRST
    """
    return _run(caller, ["inv_onhand_lot", "inv_movement_daily"], sql,
                {"d": int(days_no_movement or 180), "st": _val(subinventory_type)}, "inv_get_slow_moving", args)


def opm_get_item_cost(caller: Caller, item: str, period: str | None = None) -> dict:
    """OPM actual cost (CKDO_PMAC) of an item per costing period, with the
    previous period's cost and the change, and the cost per component.
    Without a period: the last 13 periods."""
    args = {"item": item, "period": period}
    start, end = _month_range(period)
    sql = """
        WITH c AS (
            SELECT item_code, item_desc, uom, period_code, period_start_date, period_end_date, period_status,
                   unit_cost, cost_components,
                   LAG(unit_cost) OVER (PARTITION BY item_code ORDER BY period_start_date) AS unit_cost_prev,
                   ROW_NUMBER() OVER (PARTITION BY item_code ORDER BY period_start_date DESC) AS rn
              FROM mart.opm_item_cost
             WHERE UPPER(item_code) = UPPER(%(i)s::text) OR item_desc ILIKE %(il)s::text
        )
        SELECT item_code, item_desc, uom, period_code, period_start_date, period_status, unit_cost, unit_cost_prev,
               unit_cost - unit_cost_prev AS selisih,
               ROUND(100.0 * (unit_cost - unit_cost_prev) / NULLIF(unit_cost_prev, 0), 1) AS perubahan_pct,
               cost_components
          FROM c
         WHERE (%(s)s::date IS NULL AND rn <= 13)
            OR (period_start_date <= %(e)s::date AND period_end_date >= %(s)s::date)
         ORDER BY item_code, period_start_date DESC
    """
    return _run(caller, "opm_item_cost", sql, {"i": _val(item), "il": _like(item), "s": start, "e": end},
                "opm_get_item_cost", args)


def gl_get_account_movement(caller: Caller, account: str, period_from: str, period_to: str | None = None,
                            department: str | None = None) -> dict:
    """Month-by-month movement of an account (code prefix or name): opening,
    debit, credit, closing — from the trial balance."""
    args = {"account": account, "period_from": period_from, "period_to": period_to, "department": department}
    pf = _period_name(period_from)
    pt = _period_name(period_to) or pf
    if not pf:
        raise sql_guard.SqlRejected("period_from wajib, format AUG-26 atau 2026-08.")
    key = lambda p: (2000 + int(p[4:])) * 100 + _MON.index(p[:3]) + 1  # noqa: E731
    sql = f"""
        SELECT period_name, account_code, MAX(account_desc) AS account_desc,
               SUM(begin_balance) AS saldo_awal, SUM(period_dr) AS debit, SUM(period_cr) AS kredit,
               SUM(period_dr) - SUM(period_cr) AS mutasi_net, SUM(end_balance) AS saldo_akhir
          FROM mart.gl_trial_balance
         WHERE period_year * 100 + period_num BETWEEN %(kf)s AND %(kt)s
           AND NOT is_adjustment
           AND {_ACCOUNT_FILTER}
           AND {_DEPT_FILTER}
         GROUP BY period_name, period_year, period_num, account_code
         ORDER BY account_code, period_year, period_num
    """
    return _run(caller, "gl_trial_balance", sql,
                {"kf": key(pf), "kt": key(pt), "acc": _account_term(account), "dept": _dept_term(department)},
                "gl_get_account_movement", args)


def gl_get_budget_vs_actual(caller: Caller, period: str, ytd: bool = False, department: str | None = None,
                            account: str | None = None, budget_name: str | None = None,
                            include_revenue: bool = False, group_by: str = "department") -> dict:
    """Budget vs encumbrance vs actual (ledger 2022, expense accounts unless
    include_revenue). Without budget_name the budget version with the most
    rows in that period is used and named in every row. Budget and actual
    are summed over the periods; encumbrance is a balance — what is still
    reserved at the end of the last period (reservations are relieved over
    later periods and years, so its movements do not sum). available =
    budget − encumbrance − actual; a negative encumbrance (this ledger has
    departments where relief exceeds reservations, e.g. HRGA 2025-2026) is
    shown but not subtracted, with a note in the row."""
    args = {"period": period, "ytd": ytd, "department": department, "account": account, "budget_name": budget_name,
            "include_revenue": include_revenue, "group_by": group_by}
    cond, params = _gl_period_filter(period, ytd)
    dim = {"account": "account_code, account_desc", "section": "pl_section, pl_line",
           "month": "period_name, period_year, period_num"}.get(group_by, "dept_code, dept_desc")
    params.update({"dept": _dept_term(department), "acc": _account_term(account), "bn": _val(budget_name),
                   "rev": include_revenue})
    sql = f"""
        WITH f AS (
            SELECT * FROM mart.gl_budget_vs_actual
             WHERE {cond}
               AND (%(rev)s OR account_type = 'E')
               AND {_ACCOUNT_FILTER}
               AND {_DEPT_FILTER}
        ), v AS (
            SELECT COALESCE(%(bn)s::text, (SELECT version_name FROM f WHERE kind = 'BUDGET'
                                            GROUP BY version_name ORDER BY COUNT(*) DESC LIMIT 1)) AS bv,
                   (SELECT MAX(period_year * 100 + period_num) FROM f) AS last_period
        ), agg AS (
            SELECT {dim},
                   SUM(amount) FILTER (WHERE kind = 'BUDGET' AND version_name ILIKE (SELECT bv FROM v)) AS budget_idr,
                   SUM(end_balance) FILTER (WHERE kind = 'ENCUMBRANCE'
                                              AND period_year * 100 + period_num = (SELECT last_period FROM v))
                                                                                       AS encumbrance_idr,
                   SUM(amount) FILTER (WHERE kind = 'ACTUAL') AS actual_idr
              FROM f GROUP BY {dim}
        )
        SELECT agg.*,
               COALESCE(budget_idr, 0) - GREATEST(COALESCE(encumbrance_idr, 0), 0) - COALESCE(actual_idr, 0)
                                                                                       AS available_idr,
               ROUND(100.0 * actual_idr / NULLIF(budget_idr, 0), 1) AS realisasi_pct,
               CASE WHEN encumbrance_idr < 0
                    THEN 'Encumbrance negatif di GL (relief melebihi reservasi) — tidak dikurangkan dari sisa budget'
               END AS catatan,
               (SELECT bv FROM v) AS budget_name
          FROM agg
         WHERE COALESCE(budget_idr, 0) <> 0 OR COALESCE(actual_idr, 0) <> 0 OR COALESCE(encumbrance_idr, 0) <> 0
         ORDER BY COALESCE(budget_idr, 0) + COALESCE(actual_idr, 0) DESC
    """
    return _run(caller, "gl_budget_vs_actual", sql, params, "gl_get_budget_vs_actual", args)


# ── PAC Business Plan (pac_sql.py) ───────────────────────────────────────────

_BP_SECTIONS = {
    "p&l": "1", "pl": "1", "profit": "1", "laba rugi": "1", "sales": "2", "penjualan": "2",
    "cogs": "3", "hpp": "3", "manufactur": "4", "produksi": "4", "invest": "5", "capex": "5",
    "purchas": "6", "pembelian": "6", "registra": "7", "marketing": "8", "personnel": "9", "personel": "9",
    "karyawan": "9", "headcount": "9", "cashflow": "10", "cash flow": "10", "arus kas": "10",
}


def _bp_section(v: str | None) -> str | None:
    """'1-2', '2', 'cogs', 'Sales Plan' -> a section code. A bare number
    takes the whole family ('1' -> 1-1, 1-2, 1-2.a…, never 10); a code with
    a dash or dot is that sheet only ('1-2' is the summary, not 1-2.a), since
    the per-business sheets repeat the summary's line names."""
    import re as _re
    v = _val(v)
    if not v:
        return None
    m = _re.match(r"^\s*(\d+(?:-\d+)?(?:\.[a-z])?)\s*$", v)
    if m:
        return m.group(1)
    low = v.lower()
    for word, pattern in _BP_SECTIONS.items():
        # Word start always; short keys (pl, hpp, ...) must be whole words, so
        # "Sales Plan" is not read as "pl".
        end = r"(?![a-z])" if len(word) <= 4 else ""
        if _re.search(rf"(?<![a-z]){_re.escape(word)}{end}", low):
            return pattern
    raise sql_guard.SqlRejected(f"Bagian '{v}' tidak dikenal — pakai nomor (1-1, 1-2, 2-1, 3-1, 4, 5, 6-1, 9, 10) "
                                "atau nama (P&L, sales, COGS, manufacture, investment, purchase, personnel, cashflow).")


def _bp_period(period: str | None) -> tuple:
    """'2026' -> year columns of 2026; '2026-03' -> March 2026; '2026-Q1' -> Q1;
    'tahunan' -> every year column (plan total and prior-year comparison)."""
    import re as _re
    if not period:
        return None, None, None
    if str(period).strip().lower() in ("tahunan", "year", "yearly", "annual"):
        return 0, None, None
    m = _re.match(r"^\s*(\d{4})(?:-(?:(\d{1,2})|[Qq]([1-4])))?\s*$", str(period))
    if not m:
        raise sql_guard.SqlRejected(f"Format periode '{period}' tidak dikenal — pakai YYYY, YYYY-MM atau YYYY-Qn.")
    return int(m.group(1)), (int(m.group(2)) if m.group(2) else None), (int(m.group(3)) if m.group(3) else None)


def pac_get_business_plan(caller: Caller, year: int | None = None, section: str | None = None,
                          line: str | None = None, period: str | None = None, scenario: str | None = None,
                          measure: str | None = None) -> dict:
    """Business Plan figures. Without section/line it lists the sections of
    that year's plan instead of 16k cells, so the model can pick one."""
    args = {"year": year, "section": section, "line": line, "period": period, "scenario": scenario,
            "measure": measure}
    py, pm, pq = _bp_period(period)
    params = {"year": year, "sec": _bp_section(section), "line": _like(line), "py": py, "pm": pm, "pq": pq,
              "sc": _val(scenario), "ms": _val(measure)}
    year_cond = "plan_year = COALESCE(%(year)s::int, (SELECT MAX(plan_year) FROM mart.pac_business_plan))"
    if not params["sec"] and not params["line"]:
        sql = f"""
            SELECT plan_year, section, sheet_title, MAX(unit) AS unit, COUNT(DISTINCT line_path) AS jml_baris,
                   COUNT(*) FILTER (WHERE period_type = 'month') AS sel_bulanan
              FROM mart.pac_business_plan WHERE {year_cond}
             GROUP BY plan_year, section, sheet_title
             ORDER BY SUBSTRING(section FROM '^[0-9]+')::int NULLS FIRST, section
        """
        res = _run(caller, "pac_business_plan", sql, params, "pac_get_business_plan", args)
        res["note"] = ("Daftar bagian Business Plan. Panggil lagi dengan section (mis. '1-2') dan/atau line "
                       "(mis. 'Net Sales') untuk angkanya.")
        return res
    # A month or quarter asks for that column; a bare year asks for the year
    # columns (plan total and the prior-year comparison the document carries).
    sql = f"""
        SELECT plan_year, section, sheet_title, line_path, column_header, period_type, period_year,
               period_month, period_quarter, scenario, measure, unit,
               amount_idr, amount_in_unit, quantity, pct, keterangan
          FROM mart.pac_business_plan
         WHERE {year_cond}
           AND (%(sec)s::text  IS NULL OR section = %(sec)s::text
                OR (%(sec)s::text !~ '[-.]' AND (section LIKE %(sec)s::text || '-%%'
                                                 OR section LIKE %(sec)s::text || '.%%')))
           AND (%(line)s::text IS NULL OR line_path ILIKE %(line)s::text)
           AND (%(sc)s::text   IS NULL OR scenario = LOWER(%(sc)s::text))
           AND (%(ms)s::text   IS NULL OR measure = LOWER(%(ms)s::text))
           AND (%(pm)s::int IS NULL OR (period_type = 'month' AND period_month = %(pm)s::int
                                        AND period_year = %(py)s::int))
           AND (%(pq)s::int IS NULL OR (period_type = 'quarter' AND period_quarter = %(pq)s::int))
           AND (%(py)s::int IS NULL OR %(pm)s::int IS NOT NULL OR %(pq)s::int IS NOT NULL
                OR (period_type = 'year' AND (%(py)s::int = 0 OR period_year = %(py)s::int)))
         ORDER BY section, row_no, col_no
    """
    res = _run(caller, "pac_business_plan", sql, params, "pac_get_business_plan", args)
    if res.get("truncated"):
        res["note"] = ("Hasil terpotong 500 baris — jangan menyimpulkan total dari hasil ini. Persempit: period='YYYY' "
                       "(kolom tahunan saja), period='YYYY-MM', section sheet tertentu (mis. '1-1'), atau line.")
    return res


# Business Plan P&L line each basis reads. EBS invoices (RA, net of credit
# memos) are CKD OTTO's own sales to its customers — closest to the plan's
# "CKD OTTO, Gross Sales". Net Sales is after distribution fee, discount,
# return and freight, which are not on the invoice; "Customer Sales" is the
# distributors' sales to the market.
_BP_BASIS = {"gross": "CKD OTTO, Gross Sales", "net": "CKD OTTO, Net Sales", "customer": "Customer Sales"}


def pac_get_sales_plan_vs_actual(caller: Caller, year: int, month: int | None = None, ytd: bool = False,
                                 basis: str = "gross", group_by: str = "business") -> dict:
    """Business Plan sales (P&L monthly, section 1-2) vs sales invoiced in
    EBS, per business (Local / CMO / Export), for one month, year to date
    up to a month, or the whole year."""
    args = {"year": year, "month": month, "ytd": ytd, "basis": basis, "group_by": group_by}
    line = _BP_BASIS.get((basis or "gross").strip().lower())
    if not line:
        raise sql_guard.SqlRejected("basis harus gross, net atau customer.")
    if month is not None and not 1 <= int(month) <= 12:
        raise sql_guard.SqlRejected("month harus 1–12.")
    if month:
        m0, m1 = (1, int(month)) if ytd else (int(month), int(month))
    else:
        m0, m1 = 1, 12
    dims = {"month": ["period_start_date"], "business_month": ["period_start_date", "bisnis"]}.get(group_by, ["bisnis"])
    dim = ", ".join(dims)
    nulls = ", ".join("NULL" for _ in dims)
    shown = ", ".join("COALESCE(bisnis, 'TOTAL') AS bisnis" if d == "bisnis" else d for d in dims)
    params = {"year": int(year), "line": line, "m0": m0, "m1": m1}
    sql = f"""
        WITH plan AS (
            SELECT period_start_date,
                   CASE WHEN line_label ILIKE 'Local%%'  THEN 'Local'
                        WHEN line_label ILIKE 'CMO%%'    THEN 'CMO'
                        WHEN line_label ILIKE 'Export%%' THEN 'Export' ELSE line_label END AS bisnis,
                   amount_idr
              FROM mart.pac_business_plan
             WHERE plan_year = %(year)s AND section = '1-2' AND period_type = 'month' AND measure = 'value'
               AND line_path LIKE %(line)s || ' > %%' AND line_level = 2
               AND period_month BETWEEN %(m0)s AND %(m1)s
        ), actual AS (
            SELECT period_start_date, business_type AS bisnis, amount_idr
              FROM mart.sales_by_customer_item_month
             WHERE period_start_date >= make_date(%(year)s, %(m0)s, 1)
               AND period_start_date <  make_date(%(year)s, %(m1)s, 1) + INTERVAL '1 month'
        ), agg AS (
            SELECT {dim}, SUM(plan_idr) AS plan_idr, SUM(actual_idr) AS actual_idr
              FROM (SELECT {dim}, amount_idr AS plan_idr, NULL::numeric AS actual_idr FROM plan
                    UNION ALL
                    SELECT {dim}, NULL, amount_idr FROM actual) u
             GROUP BY {dim}
        ), tot AS (
            SELECT {dim}, plan_idr, actual_idr, 0 AS ord FROM agg
            UNION ALL
            SELECT {nulls}, SUM(plan_idr), SUM(actual_idr), 1 FROM agg
        )
        SELECT {shown},
               ROUND(COALESCE(plan_idr, 0)) AS plan_idr, ROUND(COALESCE(actual_idr, 0)) AS actual_idr,
               ROUND(COALESCE(actual_idr, 0) - COALESCE(plan_idr, 0)) AS selisih_idr,
               ROUND(100.0 * actual_idr / NULLIF(plan_idr, 0), 1) AS pencapaian_pct
          FROM tot ORDER BY ord, {dim}
    """
    res = _run(caller, ["pac_business_plan", "sales_by_customer_item_month"], sql, params,
               "pac_get_sales_plan_vs_actual", args)
    res["note"] = (f"Plan = Business Plan {year}, baris '{line}' (P&L bulanan, bagian 1-2), bulan {m0}–{m1}. "
                   "Actual = penjualan terinvoice di Oracle EBS (RA, dikurangi credit memo) per tipe bisnis; "
                   "'Non-SO' = invoice tanpa sales order, tidak punya padanan di plan. Bulan berjalan belum lengkap. "
                   "Basis gross paling sebanding dengan invoice EBS; net sudah dikurangi distribution fee, diskon, "
                   "retur dan freight yang tidak tercatat di invoice.")
    return res
