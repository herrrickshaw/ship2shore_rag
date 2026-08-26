"""Create the pgvector extension + literature schema + operations schema.
Idempotent — safe to re-run. Only applies to the Postgres (shore-side)
backend; the SQLite (vessel-side) operations schema self-creates on first
connect (see ops/store.py) since there's no separate init step at sea."""

import psycopg

from config import DATABASE_URL, ROOT


def main() -> None:
    schema_sql = (ROOT / "db" / "schema.sql").read_text()
    ops_schema_sql = (ROOT / "db" / "ops_schema.sql").read_text()
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute(schema_sql)
        conn.execute(ops_schema_sql)
    print(f"schema ready at {DATABASE_URL}")


if __name__ == "__main__":
    main()
