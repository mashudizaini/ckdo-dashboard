#!/usr/bin/env python3
"""
Emit the DDL needed to bring a deployed database up to date with the models.

Why this exists: app/main.py only runs Base.metadata.create_all() when
ENVIRONMENT=development, so the dev and production databases never pick up new
tables on their own. And even where create_all() does run it never ALTERs an
existing table — a column added to a model that already has a table is silently
skipped. Both gaps only surface later as a 500 on a column that isn't there.

This compares Base.metadata against the live database and prints the missing
CREATE TABLE / CREATE INDEX / ALTER TABLE ADD COLUMN statements. Nothing is
executed unless --apply is passed, so the default is safe to run anywhere.

    docker compose exec backend python scripts/sync_schema.py                  # review
    docker compose exec -T backend python scripts/sync_schema.py > migrate.sql # capture
    docker compose exec backend python scripts/sync_schema.py --apply          # execute

Every statement is idempotent (IF NOT EXISTS), so re-running changes nothing.
"""

import argparse
import datetime
import importlib
import os
import pkgutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy import inspect, text                      # noqa: E402
from sqlalchemy.dialects import postgresql                # noqa: E402
from sqlalchemy.schema import CreateIndex, CreateTable    # noqa: E402

from app.database import Base, sync_engine                # noqa: E402

DIALECT = postgresql.dialect()


def load_all_models():
    """app/models/__init__.py only re-exports a couple of names, so importing
    the package is not enough to populate Base.metadata — every module under it
    has to be imported for its tables to register."""
    import app.models as pkg
    for mod in pkgutil.iter_modules(pkg.__path__):
        importlib.import_module(f"app.models.{mod.name}")


def sql_literal(value):
    """Render a Python-side column default as a SQL literal, or None when it
    isn't something we can safely inline (callables like datetime.utcnow)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return None


def column_default(col):
    if col.server_default is not None:
        return str(getattr(col.server_default, "arg", col.server_default))
    if col.default is not None and getattr(col.default, "is_scalar", False):
        return sql_literal(col.default.arg)
    return None


def add_column_ddl(table, col):
    type_sql = col.type.compile(dialect=DIALECT)
    parts = [f"ALTER TABLE {table.name} ADD COLUMN IF NOT EXISTS {col.name} {type_sql}"]
    default = column_default(col)
    if default is not None:
        parts.append(f"DEFAULT {default}")

    if not col.nullable and default is None:
        # NOT NULL with no default would fail outright on a table that already
        # has rows. Add it nullable so the migration still runs, and leave the
        # backfill as an explicit decision rather than a silent one.
        return (
            f"-- REVIEW: {table.name}.{col.name} is NOT NULL in the model but has no\n"
            f"-- default, which cannot be applied to a table with existing rows.\n"
            f"-- Added as nullable; backfill it, then run:\n"
            f"--   ALTER TABLE {table.name} ALTER COLUMN {col.name} SET NOT NULL;\n"
            + " ".join(parts) + ";"
        )

    if not col.nullable:
        parts.append("NOT NULL")
    return " ".join(parts) + ";"


def build_plan():
    load_all_models()
    insp = inspect(sync_engine)
    existing_tables = set(insp.get_table_names())

    new_tables, altered = [], []
    statements = []

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            new_tables.append(table.name)
            statements.append(
                str(CreateTable(table, if_not_exists=True).compile(dialect=DIALECT)).strip() + ";"
            )
            for idx in sorted(table.indexes, key=lambda i: i.name or ""):
                statements.append(
                    str(CreateIndex(idx, if_not_exists=True).compile(dialect=DIALECT)).strip() + ";"
                )
            continue

        live_cols = {c["name"] for c in insp.get_columns(table.name)}
        live_idx = {i["name"] for i in insp.get_indexes(table.name)}

        for col in table.columns:
            if col.name not in live_cols:
                altered.append(f"{table.name}.{col.name}")
                statements.append(add_column_ddl(table, col))

        for idx in sorted(table.indexes, key=lambda i: i.name or ""):
            if idx.name not in live_idx:
                statements.append(
                    str(CreateIndex(idx, if_not_exists=True).compile(dialect=DIALECT)).strip() + ";"
                )

    return new_tables, altered, statements


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="execute the statements instead of only printing them")
    args = ap.parse_args()

    new_tables, altered, statements = build_plan()

    header = [
        "-- Generated by backend/scripts/sync_schema.py on "
        + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        f"-- Missing tables : {len(new_tables)}",
        f"-- Missing columns: {len(altered)}",
    ]
    for name in new_tables:
        header.append(f"--   CREATE {name}")
    for name in altered:
        header.append(f"--   ADD    {name}")

    print("\n".join(header))

    if not statements:
        print("-- Database already matches the models; nothing to do.")
        return

    print("\nBEGIN;\n")
    print("\n\n".join(statements))
    print("\nCOMMIT;")

    if not args.apply:
        print("\n-- Dry run. Re-run with --apply to execute.", file=sys.stderr)
        return

    with sync_engine.begin() as conn:
        for stmt in statements:
            body = "\n".join(
                line for line in stmt.splitlines() if not line.strip().startswith("--")
            ).strip()
            if body:
                conn.execute(text(body))
    print(f"\n-- Applied {len(statements)} statement(s).", file=sys.stderr)


if __name__ == "__main__":
    main()
