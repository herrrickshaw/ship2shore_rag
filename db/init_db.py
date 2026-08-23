"""Create the pgvector extension and schema. Idempotent — safe to re-run."""
import psycopg

from config import DATABASE_URL, ROOT


def main() -> None:
    schema_sql = (ROOT / "db" / "schema.sql").read_text()
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute(schema_sql)
    print(f"schema ready at {DATABASE_URL}")


if __name__ == "__main__":
    main()
