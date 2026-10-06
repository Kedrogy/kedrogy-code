"""Real PostgreSQL import invariants and runtime privilege boundaries."""

import copy
import json
import os
import sys
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg import sql

from mykedro.sources import SourceError, import_records, prepare

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from configure_sources import create_source, install

ROWS = [{"id": "001", "text": "First product", "source": "synthetic"},
        {"id": "002", "text": "O'Reilly: отзывы ", "source": "synthetic"}]


class SourceInputTests(unittest.TestCase):
    def test_string_ids_and_exact_text(self):
        rows, digest, duplicates = prepare(ROWS, "upstream-id-v1")
        self.assertEqual(rows[0]["external_key"], "001")
        self.assertEqual(rows[1]["text"], "O'Reilly: отзывы ")
        self.assertEqual(prepare(list(reversed(ROWS)), "upstream-id-v1")[1], digest)
        self.assertEqual(duplicates, 0)
        for changed in [{"id": 1}, {"id": None}, {"text": ""}, {"text": "a" * 60001}, {"meta": {"x": float("nan")}}]:
            with self.subTest(changed=changed), self.assertRaises(SourceError):
                prepare([ROWS[0] | changed], "upstream-id-v1")

    def test_content_mode_and_duplicate_accounting_are_explicit(self):
        without_ids = [{"text": "same"}, {"text": "same"}]
        with self.assertRaises(SourceError):
            prepare(without_ids, "upstream-id-v1")
        with self.assertRaises(SourceError):
            prepare(without_ids, "content-addressed-v1")
        result, digest, duplicate_count = prepare(without_ids, "content-addressed-v1", deduplicate=True)
        self.assertEqual((len(result), duplicate_count), (1, 1))
        self.assertNotEqual(digest, prepare(without_ids[:1], "content-addressed-v1", deduplicate=True)[1])


@unittest.skipUnless(os.environ.get("KEDROGY_TEST_DATABASE") == "disposable", "Requires a disposable PostgreSQL database")
class SourceDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS all_data (id text PRIMARY KEY, text text, source text)")
            conn.execute("CREATE TABLE IF NOT EXISTS dataset (id serial PRIMARY KEY, name text, session boolean DEFAULT false)")
            conn.execute("CREATE TABLE IF NOT EXISTS example (id serial PRIMARY KEY, content bytea)")
            conn.execute("CREATE TABLE IF NOT EXISTS link (dataset_id int, example_id int)")
            for kind in ("migrator", "ingest", "reader", "app"):
                role = "kedrogy_" + kind
                if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                    conn.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
            install(conn)

    def setUp(self):
        with psycopg.connect() as conn:
            conn.execute("TRUNCATE kedrogy_source.import_receipt, kedrogy_source.record, kedrogy_source.collection")
            self.source_id = create_source(conn, "synthetic", "upstream-id-v1")

    def ingest(self, rows, key, **kwargs):
        with psycopg.connect() as conn:
            conn.execute("SET ROLE kedrogy_ingest")
            conn.commit()
            return import_records(conn, "synthetic", rows, key, **kwargs)

    def records(self):
        with psycopg.connect() as conn:
            return conn.execute("SELECT id,external_key,text,provenance FROM kedrogy_source.record ORDER BY external_key").fetchall()

    def test_reorder_subset_append_and_lost_ack_replay(self):
        receipt = self.ingest(ROWS, "first")
        before = self.records()
        repeated = self.ingest(list(reversed(ROWS)), "first")
        self.assertEqual(receipt["id"], repeated["id"])
        self.assertTrue(repeated["replayed"])
        self.assertEqual(self.ingest(ROWS[:1], "subset")["inserted_count"], 0)
        self.assertEqual(before, self.records())
        added = ROWS + [{"id": "003", "text": "new"}]
        self.assertEqual(self.ingest(added, "append")["inserted_count"], 1)
        self.assertEqual(before, self.records()[:2])

    def test_conflicting_batch_rolls_back_new_records_and_receipt(self):
        self.ingest(ROWS, "first")
        before = self.records()
        with self.assertRaises(SourceError):
            self.ingest([{"id": "new", "text": "new"}, ROWS[0] | {"text": "changed"}], "conflict")
        self.assertEqual(self.records(), before)
        with psycopg.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM kedrogy_source.import_receipt WHERE request_key='conflict'").fetchone()[0], 0)
        self.assertEqual(self.ingest(ROWS, "conflict")["unchanged_count"], 2)

    def test_preview_and_failed_request_do_not_publish(self):
        result = self.ingest(ROWS, "preview", dry_run=True)
        self.assertEqual(result["inserted_count"], 2)
        self.assertEqual(self.records(), [])
        self.ingest(ROWS, "preview")
        with self.assertRaises(SourceError):
            self.ingest(ROWS[:1], "preview")
        self.assertEqual(len(self.records()), 2)

    def test_concurrent_imports_serialize_and_replay(self):
        gate = threading.Barrier(2)
        def submit(key):
            gate.wait(timeout=5)
            return self.ingest(copy.deepcopy(ROWS), key)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, ["concurrent", "concurrent"]))
        self.assertEqual(results[0]["id"], results[1]["id"])
        self.assertEqual(sum(result["replayed"] for result in results), 1)
        self.assertEqual(len(self.records()), 2)

    def test_overlapping_concurrent_imports_preserve_the_union(self):
        gate = threading.Barrier(2)
        def submit(index):
            gate.wait(timeout=5)
            return self.ingest([ROWS[0], {"id": f"new-{index}", "text": f"new {index}"}], f"batch-{index}")
        with ThreadPoolExecutor(max_workers=2) as pool:
            receipts = list(pool.map(submit, [1, 2]))
        self.assertEqual(sum(receipt["inserted_count"] for receipt in receipts), 3)
        self.assertEqual({row[1] for row in self.records()}, {"001", "new-1", "new-2"})

    def test_failure_after_insert_before_receipt_rolls_back_everything(self):
        # A real database failure after records are inserted exercises transaction rollback.
        with psycopg.connect() as conn:
            conn.execute("REVOKE INSERT ON kedrogy_source.import_receipt FROM kedrogy_ingest")
        try:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                self.ingest(ROWS, "crash")
            self.assertEqual(self.records(), [])
        finally:
            with psycopg.connect() as conn:
                conn.execute("GRANT INSERT ON kedrogy_source.import_receipt TO kedrogy_ingest")
        self.assertEqual(self.ingest(ROWS, "crash")["inserted_count"], 2)

    def test_ingest_role_cannot_mutate_drop_or_impersonate_owner(self):
        self.ingest(ROWS, "first")
        statements = ["UPDATE kedrogy_source.record SET text='changed'", "DELETE FROM kedrogy_source.record",
                      "TRUNCATE kedrogy_source.record CASCADE", "DROP TABLE kedrogy_source.record CASCADE",
                      "UPDATE kedrogy_source.collection SET source_key='changed'", "SET ROLE kedrogy_migrator",
                      "DELETE FROM public.all_data", "DROP TABLE public.all_data",
                      "CREATE TABLE public.unapproved_source (id int)"]
        for statement in statements:
            with self.subTest(statement=statement), psycopg.connect() as conn:
                conn.execute("SET SESSION AUTHORIZATION kedrogy_ingest")
                conn.commit()
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    conn.execute(statement)
                conn.rollback()
        self.assertEqual(len(self.records()), 2)

    def test_namespace_keys_do_not_collide(self):
        self.ingest(ROWS, "first")
        with psycopg.connect() as conn:
            create_source(conn, "other", "upstream-id-v1")
        with psycopg.connect() as conn:
            import_records(conn, "other", ROWS, "first")
        self.assertEqual(len({row[0] for row in self.records()}), 4)

    def test_reader_exclusion_requires_both_source_and_record_identity(self):
        from mykedro.db_queries import read_examples
        self.ingest(ROWS[:1], "first")
        record_id = str(self.records()[0][0])
        dataset_name = "synthetic-exclusion-" + str(uuid.uuid4())
        payload = {"meta": {"_record_id": record_id, "_source_id": str(uuid.uuid4())}}
        with psycopg.connect() as conn:
            dataset_id = conn.execute("INSERT INTO dataset(name) VALUES (%s) RETURNING id", (dataset_name,)).fetchone()[0]
            example_id = conn.execute("INSERT INTO example(content) VALUES (%s) RETURNING id", (json.dumps(payload).encode(),)).fetchone()[0]
            conn.execute("INSERT INTO link VALUES (%s,%s)", (dataset_id, example_id))
        registry = {"managed": {"schema": "kedrogy_source", "table": "record", "id_fields": ["id"], "source_id": str(self.source_id)}}
        with patch.dict(os.environ, {"KEDROGY_SOURCES": json.dumps(registry)}):
            self.assertEqual(len(read_examples(dataset_name=dataset_name, table_name="managed", id_field="id")), 1)
            payload["meta"]["_source_id"] = str(self.source_id)
            with psycopg.connect() as conn:
                conn.execute("UPDATE example SET content=%s WHERE id=%s", (json.dumps(payload).encode(), example_id))
            self.assertEqual(read_examples(dataset_name=dataset_name, table_name="managed", id_field="id"), [])
