"""Preview an approved legacy source without copying rows or changing bindings."""

import argparse
import json
from dataclasses import asdict

import psycopg
from psycopg import sql

from mykedro.db_queries import source_spec


def preview(connection, source):
    if source.source_id is not None:
        raise ValueError("This preview is for legacy sources, not managed collections.")
    row = connection.execute(sql.SQL("""
        SELECT count(*), count(*) FILTER (WHERE {id} IS NULL),
               count(*) FILTER (WHERE text IS NULL OR btrim(text)=''),
               count({id}) - count(DISTINCT {id})
        FROM {table}
    """).format(id=sql.Identifier(source.id_field),
                table=sql.Identifier(source.schema, source.table))).fetchone()
    return {"applied": False, "source": asdict(source), "rows": row[0],
            "missing_ids": row[1], "empty_texts": row[2], "duplicate_ids": row[3],
            "identity_verified": False,
            "next_step": "Review the origin of legacy IDs. Copy only into a new explicitly selected source namespace, retaining original source and ID provenance. Existing annotations remain bound to their original source."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--id-field", default="id")
    args = parser.parse_args()
    source = source_spec(args.source, args.id_field)
    with psycopg.connect(options="-c default_transaction_read_only=on -c statement_timeout=15000") as connection:
        result = preview(connection, source)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
