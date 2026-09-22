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

from sqlalchemy import MetaData, create_engine, inspect, text  # noqa: E402
from sqlalchemy.dialects import postgresql                # noqa: E402
from sqlalchemy.schema import CreateIndex, CreateTable    # noqa: E402

from app.config import get_settings                       # noqa: E402
from app.database import Base                             # noqa: E402

DIALECT = postgresql.dialect()


def make_sync_engine():
    """Build our own psycopg2 engine rather than reusing database.py's
    sync_engine. That one is create_engine(settings.database_url) verbatim, so
    it only works when DATABASE_URL carries the plain postgresql:// scheme —
    the convention the code assumes, since the +asyncpg driver is meant to be
    added at the point of use. Where a deployment has baked +asyncpg into the
    env var instead, sync_engine is an async-dialect engine driven
    synchronously and every use of it dies with MissingGreenlet. Normalising
    here keeps this script usable for diagnosing exactly that kind of
    environment."""
    url = get_settings().database_url
    url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return create_engine(url)


def load_all_models():
    """Import every module under app/models and return them.

    app/models/__init__.py only re-exports a couple of names, so importing the
    package is not enough for the tables to register."""
    import app.models as pkg
    modules = []
    for mod in pkgutil.iter_modules(pkg.__path__):
        modules.append(importlib.import_module(f"app.models.{mod.name}"))
    return modules


def collect_metadata(modules):
    """Gather every MetaData the models use, not just app.database.Base's.

    ebs_backup, vpn_monitor, hikcentral and zkteco each call declarative_base()
    of their own, so their tables live in separate MetaData objects that are
    invisible to Base.metadata. Those four create their tables through their own
    init_*_db() at startup, but only a scan that walks every registry can say
    whether a deployment actually has them."""
    found = {}
    for module in modules:
        for obj in vars(module).values():
            md = getattr(obj, "metadata", None)
            if isinstance(md, MetaData):
                found.setdefault(id(md), md)
    found.setdefault(id(Base.metadata), Base.metadata)

    tables, seen = [], set()
    for md in found.values():
        for table in md.sorted_tables:
            if table.name not in seen:
                seen.add(table.name)
                tables.append(table)
    return tables


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
    tables = collect_metadata(load_all_models())
    engine = make_sync_engine()
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())

    new_tables, altered = [], []
    statements = []

    for table in tables:
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

    return new_tables, altered, statements, engine


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="execute the statements instead of only printing them")
    args = ap.parse_args()

    new_tables, altered, statements, engine = build_plan()

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

    with engine.begin() as conn:
        for stmt in statements:
            body = "\n".join(
                line for line in stmt.splitlines() if not line.strip().startswith("--")
            ).strip()
            if body:
                conn.execute(text(body))
    print(f"\n-- Applied {len(statements)} statement(s).", file=sys.stderr)


if __name__ == "__main__":
    main()
