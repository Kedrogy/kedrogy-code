"""Explicit transactional ingestion; catalog saves cannot replace source tables."""

import psycopg

from mykedro.sources import import_records


def ingest(all_data, parameters: dict) -> dict:
    if not parameters.get("source_key") or not parameters.get("request_key"):
        raise ValueError("Set an approved source_key and a stable request_key before importing.")
    with psycopg.connect() as connection:
        return import_records(connection, parameters["source_key"], all_data.to_dict("records"),
            parameters["request_key"], dry_run=not parameters.get("apply", False),
            deduplicate=parameters.get("deduplicate", False))
