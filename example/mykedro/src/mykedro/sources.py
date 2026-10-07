"""Append-only source imports with stable identity and transactional receipts."""

import argparse
import csv
import hashlib
import json
import re
import uuid
from collections import Counter
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

PARSER_VERSION = "source-record-v1"
MAX_ROWS = 100000
MAX_BYTES = 64 * 1024 * 1024


class SourceError(ValueError):
    """An import conflict with no source text or credentials in the diagnostic."""


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise SourceError("Source metadata must contain finite JSON values.") from error


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def read_file(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise SourceError("The source file exceeds the 64 MiB import limit.")
    with path.open(encoding="utf-8", newline="") as file:
        if path.suffix.lower() == ".csv":
            rows = list(csv.DictReader(file))
        elif path.suffix.lower() == ".jsonl":
            rows = [json.loads(line) for line in file if line.strip()]
        else:
            raise SourceError("Use a UTF-8 CSV or JSONL file.")
    if not 1 <= len(rows) <= MAX_ROWS:
        raise SourceError("Import between 1 and 100000 records.")
    return rows


def prepare(rows, policy, *, deduplicate=False):
    if policy not in ("upstream-id-v1", "content-addressed-v1"):
        raise SourceError("Unknown source identity policy.")
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS:
        raise SourceError("Import between 1 and 100000 records.")
    records, multiset, duplicates, total_bytes = {}, Counter(), 0, 0
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise SourceError(f"Record {index} must be an object.")
        text = row.get("text")
        if not isinstance(text, str) or not text.strip() or len(text.encode()) > 60000 or "\x00" in text:
            raise SourceError(f"Record {index} requires nonempty text of at most 60000 UTF-8 bytes, without NUL.")
        provenance = row.get("meta", {})
        if isinstance(provenance, str):
            try:
                provenance = json.loads(provenance)
            except ValueError as error:
                raise SourceError(f"Record {index} has invalid JSON metadata.") from error
        if not isinstance(provenance, dict):
            raise SourceError(f"Record {index} metadata must be an object.")
        provenance = dict(provenance)
        if "source" in row:
            provenance["source"] = row["source"]
        if len(canonical(provenance).encode()) > 16384 or "\\u0000" in canonical(provenance):
            raise SourceError(f"Record {index} metadata is invalid or exceeds 16384 bytes.")
        content = fingerprint({"text": text, "provenance": provenance})
        total_bytes += len(text.encode()) + len(canonical(provenance).encode())
        if total_bytes > MAX_BYTES:
            raise SourceError("The parsed source exceeds the 64 MiB import limit.")
        key = row.get("id", provenance.get("id")) if policy == "upstream-id-v1" else content
        if not isinstance(key, str) or not key or len(key) > 512 or any(ord(c) < 32 for c in key):
            raise SourceError(f"Record {index} requires an explicit string ID of at most 512 characters. Numeric coercion is not allowed.")
        value = {"external_key": key, "text": text, "provenance": provenance, "content_digest": content}
        multiset[fingerprint(value)] += 1
        if key in records:
            if records[key] != value or not deduplicate:
                raise SourceError(f"Record {index} duplicates an identity. Fix the input or explicitly deduplicate identical records.")
            duplicates += 1
        else:
            records[key] = value
    digest = fingerprint({"parser": PARSER_VERSION, "policy": policy, "deduplicate": deduplicate,
                          "records": sorted(multiset.items())})
    return list(records.values()), digest, duplicates


def import_records(connection, source_key, rows, request_key, *, dry_run=False, deduplicate=False):
    """Commit records and receipt atomically; callers reuse request_key after lost ACKs."""
    if not isinstance(request_key, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", request_key):
        raise SourceError("Use an ASCII request key of at most 128 characters.")
    if connection.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
        raise SourceError("Import requires a connection without an open transaction.")
    with connection.transaction(), connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute("SET LOCAL statement_timeout = '30s'")
        cursor.execute("SET LOCAL lock_timeout = '10s'")
        cursor.execute("SELECT id, identity_policy FROM kedrogy_source.collection WHERE source_key=%s", (source_key,))
        source = cursor.fetchone()
        if source is None:
            raise SourceError("The source namespace is not registered. Create it with the setup role first.")
        prepared, digest, duplicates = prepare(rows, source["identity_policy"], deduplicate=deduplicate)
        source_id = source["id"]
        # Collisions only serialize unrelated imports; uniqueness always uses the full UUID/key.
        lock_key = int.from_bytes(hashlib.sha256(b"kedrogy-source-import-v1:" + source_id.bytes).digest()[:8], "big", signed=True)
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))
        cursor.execute("SELECT * FROM kedrogy_source.import_receipt WHERE source_id=%s AND request_key=%s", (source_id, request_key))
        previous = cursor.fetchone()
        if previous:
            if previous["fingerprint"] != digest:
                raise SourceError("The request key was already used for different input.")
            return dict(previous) | {"replayed": True, "dry_run": dry_run}
        cursor.execute("""CREATE TEMP TABLE source_import_stage (
            external_key varchar(512) PRIMARY KEY, text text NOT NULL,
            provenance jsonb NOT NULL, content_digest char(64) NOT NULL
        ) ON COMMIT DROP""")
        with cursor.copy("COPY source_import_stage (external_key,text,provenance,content_digest) FROM STDIN") as copy:
            for record in prepared:
                copy.write_row((record["external_key"], record["text"], Jsonb(record["provenance"]), record["content_digest"]))
        cursor.execute("""SELECT count(*) AS count FROM source_import_stage s
            JOIN kedrogy_source.record r ON r.source_id=%s AND r.external_key=s.external_key
            WHERE r.content_digest<>s.content_digest OR r.text<>s.text OR r.provenance<>s.provenance""", (source_id,))
        conflicts = cursor.fetchone()["count"]
        if conflicts:
            raise SourceError(f"{conflicts} existing source identities have different content. Nothing was imported; use a new source namespace for corrections.")
        cursor.execute("""SELECT count(*) AS count FROM source_import_stage s
            JOIN kedrogy_source.record r ON r.source_id=%s AND r.external_key=s.external_key""", (source_id,))
        unchanged = cursor.fetchone()["count"]
        receipt = {"id": uuid.uuid4(), "source_id": source_id, "request_key": request_key,
                   "fingerprint": digest, "parser_version": PARSER_VERSION, "identity_policy": source["identity_policy"],
                   "input_count": len(rows), "inserted_count": len(prepared) - unchanged,
                   "unchanged_count": unchanged, "duplicate_count": duplicates}
        if not dry_run:
            # UUIDv5 is a stable public identifier; database uniqueness also covers namespace/key.
            cursor.executemany("""INSERT INTO kedrogy_source.record (id,source_id,external_key,text,provenance,content_digest)
                SELECT %s,%s,%s,%s,%s,%s WHERE NOT EXISTS (
                    SELECT 1 FROM kedrogy_source.record WHERE source_id=%s AND external_key=%s)""",
                [(uuid.uuid5(source_id, r["external_key"]), source_id, r["external_key"], r["text"], Jsonb(r["provenance"]),
                  r["content_digest"], source_id, r["external_key"]) for r in prepared])
            cursor.execute("""INSERT INTO kedrogy_source.import_receipt
                (id,source_id,request_key,fingerprint,parser_version,identity_policy,input_count,inserted_count,unchanged_count,duplicate_count)
                VALUES (%(id)s,%(source_id)s,%(request_key)s,%(fingerprint)s,%(parser_version)s,%(identity_policy)s,
                        %(input_count)s,%(inserted_count)s,%(unchanged_count)s,%(duplicate_count)s)
                RETURNING recorded_at""", receipt)
            receipt |= cursor.fetchone()
        return receipt | {"replayed": False, "dry_run": dry_run}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--source", required=True)
    parser.add_argument("--request-key", required=True)
    parser.add_argument("--apply", action="store_true", help="Commit the import; default is a dry run.")
    parser.add_argument("--deduplicate", action="store_true", help="Collapse identical duplicate identities and report their count.")
    args = parser.parse_args()
    with psycopg.connect() as connection:
        result = import_records(connection, args.source, read_file(args.path), args.request_key,
                                dry_run=not args.apply, deduplicate=args.deduplicate)
    print(json.dumps(result, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
