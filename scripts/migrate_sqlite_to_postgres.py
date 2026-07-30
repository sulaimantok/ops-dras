#!/usr/bin/env python3
"""Copy existing ops-dras SQLite data into an already-migrated PostgreSQL DB.

The source database is read-only. Run `alembic upgrade head` against the
target first, then run this script once while ops-dras is stopped.
"""
import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, select, text

# Running a file inside scripts/ does not put the repository root on
# sys.path, unlike `python -m ...`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schema import clusters, tasks, users


TABLES = (users, clusters, tasks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="SQLite source URL, e.g. sqlite:////path/ops-dras.sqlite3")
    parser.add_argument("--target", required=True, help="PostgreSQL target DATABASE_URL")
    args = parser.parse_args()

    source_engine = create_engine(args.source)
    target_engine = create_engine(args.target, pool_pre_ping=True)
    source_tables = set(inspect(source_engine).get_table_names())
    target_tables = set(inspect(target_engine).get_table_names())
    required = {table.name for table in TABLES}
    if not required.issubset(source_tables):
        sys.exit(f"Source is missing tables: {', '.join(sorted(required - source_tables))}")
    if not required.issubset(target_tables):
        sys.exit("Target schema is missing. Run `alembic upgrade head` first.")

    with target_engine.begin() as target:
        if any(target.execute(select(table.c.id).limit(1)).first() for table in TABLES):
            sys.exit("Target database is not empty; refusing to merge data.")
        with source_engine.connect() as source:
            for table in TABLES:
                rows = [dict(row) for row in source.execute(select(table)).mappings()]
                if rows:
                    target.execute(table.insert(), rows)
                print(f"Copied {len(rows)} row(s) to {table.name}")
        if target.dialect.name == "postgresql":
            for table in TABLES:
                target.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{table.name}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table.name}), 1), true)"
                ))
    print("Migration complete. Keep the SQLite file as a rollback backup until validation is complete.")


if __name__ == "__main__":
    main()
