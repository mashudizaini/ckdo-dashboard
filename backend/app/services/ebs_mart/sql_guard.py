"""
run_sql validation (blueprint section 7, "Guardrail wajib di tool server").

The model may write its own SQL for ad-hoc questions, but only one read-only
query over mart.*. This module decides whether a string is such a query; it
does not execute anything.

Three layers stand behind it, and none of them trusts the others:
  1. this parser check — one statement, a query, only mart.* tables, no
     dangerous functions;
  2. the connection — a read-only transaction with statement_timeout, as a
     role (llm_ro) that has SELECT on mart/meta and nothing else;
  3. the row cap — the query is wrapped and limited to MAX_ROWS + 1.

What is executed is the SQL regenerated from the parsed tree, not the string
the model sent. Whatever sqlglot understood is exactly what runs, so a
construct that parses one way here and another way in Postgres (comment
tricks, odd quoting) cannot slip a second meaning past the check.
"""
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from app.services.ebs_mart.constants import MARTS

MART_SCHEMA = "mart"

# Anything that writes, changes session state, or reaches outside the query.
_FORBIDDEN_NODES = tuple(
    getattr(exp, name) for name in (
        "Insert", "Update", "Delete", "Merge", "Create", "Drop", "Alter", "AlterTable",
        "TruncateTable", "Command", "Set", "Use", "Transaction", "Commit", "Rollback",
        "Copy", "Grant", "Into", "Lock", "LoadData", "Pragma", "Describe",
    )
    if hasattr(exp, name)
)

# Function-name prefixes and names that read files, sleep, signal other
# backends, change settings, or open connections elsewhere. The llm_ro role
# already lacks privileges for most of these; refusing them here gives the
# model a clear message instead of an opaque permission error, and keeps
# pg_sleep from occupying a connection for the full timeout.
_FORBIDDEN_FUNC_PREFIXES = ("pg_", "lo_", "dblink", "txid_", "query_to_xml", "table_to_xml", "cursor_to_xml")
_FORBIDDEN_FUNCS = {
    "set_config", "current_setting", "nextval", "setval", "currval",
    "version", "inet_server_addr", "inet_client_addr", "current_user", "session_user",
}


class SqlRejected(ValueError):
    """The query is not allowed. The message is written for the model/user."""


@dataclass
class GuardedQuery:
    sql: str                       # regenerated, schema-qualified SQL to execute
    tables: list[str] = field(default_factory=list)   # mart names referenced


def _func_name(node: exp.Expression) -> str:
    if isinstance(node, exp.Anonymous):
        return (node.name or "").lower()
    try:
        return (node.sql_name() or "").lower()
    except Exception:
        return type(node).__name__.lower()


def validate(sql: str) -> GuardedQuery:
    text = (sql or "").strip().rstrip(";").strip()
    if not text:
        raise SqlRejected("SQL kosong.")

    try:
        statements = [s for s in sqlglot.parse(text, read="postgres") if s is not None]
    except sqlglot.errors.ParseError as e:
        raise SqlRejected(f"SQL tidak bisa di-parse: {str(e).splitlines()[0]}")

    if len(statements) != 1:
        raise SqlRejected("Hanya satu statement SELECT yang diizinkan.")
    root = statements[0]

    if not isinstance(root, exp.Query):
        raise SqlRejected("Hanya SELECT yang diizinkan (tidak boleh INSERT/UPDATE/DELETE/DDL).")

    for node in root.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            raise SqlRejected(f"Konstruksi {type(node).__name__.upper()} tidak diizinkan; hanya SELECT read-only.")
        if isinstance(node, exp.Func):
            name = _func_name(node)
            if name in _FORBIDDEN_FUNCS or name.startswith(_FORBIDDEN_FUNC_PREFIXES):
                raise SqlRejected(f"Fungsi {name}() tidak diizinkan.")

    # FOR UPDATE / FOR SHARE on a SELECT
    for sel in root.find_all(exp.Select):
        if sel.args.get("locks"):
            raise SqlRejected("SELECT ... FOR UPDATE/SHARE tidak diizinkan.")

    cte_names = {cte.alias_or_name.lower() for cte in root.find_all(exp.CTE)}

    tables: list[str] = []
    for table in root.find_all(exp.Table):
        name = (table.name or "").lower()
        db = (table.db or "").lower()
        catalog = (table.catalog or "").lower()

        if not isinstance(table.this, exp.Identifier):
            # FROM generate_series(...), FROM some_function() etc.
            raise SqlRejected("Sumber data harus tabel mart.*, bukan fungsi.")
        if catalog:
            raise SqlRejected(f"Referensi lintas database tidak diizinkan: {table.sql(dialect='postgres')}")

        if not db and name in cte_names:
            continue
        if not db and name in MARTS:
            # The model often forgets the schema. Qualify known marts rather
            # than failing a query whose meaning is unambiguous.
            table.set("db", exp.to_identifier(MART_SCHEMA))
            db = MART_SCHEMA

        if db != MART_SCHEMA:
            label = f"{db}.{name}" if db else name
            raise SqlRejected(f"Tabel di luar mart tidak diizinkan: {label}. Gunakan hanya mart.* (lihat find_marts).")
        if name not in MARTS:
            raise SqlRejected(f"Mart tidak dikenal: mart.{name}. Gunakan find_marts untuk melihat mart yang tersedia.")
        if not MARTS[name].get("built"):
            raise SqlRejected(f"mart.{name} belum dibangun (fase {MARTS[name]['phase']}).")
        if name not in tables:
            tables.append(name)

    if not tables:
        raise SqlRejected("Query harus membaca minimal satu tabel mart.*.")

    return GuardedQuery(sql=root.sql(dialect="postgres", comments=False), tables=tables)
