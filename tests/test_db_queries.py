"""Run against an explicitly supplied disposable PostgreSQL database."""
import json
import os
import unittest
from unittest.mock import patch

import psycopg
from mykedro.db_queries import read_annotations, read_examples
from psycopg import sql


@unittest.skipUnless(os.environ.get('KEDROGY_TEST_DATABASE') == 'disposable', 'Requires a disposable PostgreSQL database')
class QueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect() as conn:
            conn.execute('CREATE TABLE dataset (id serial PRIMARY KEY, name text, session boolean DEFAULT false)')
            conn.execute('CREATE TABLE example (id serial PRIMARY KEY, content bytea)')
            conn.execute('CREATE TABLE link (dataset_id int, example_id int)')
            conn.execute('CREATE TABLE all_data (id text PRIMARY KEY, text text, source text)')
            conn.execute(sql.SQL("CREATE TABLE {} ({} text PRIMARY KEY, text text, source text)").format(sql.Identifier("quoted.table"), sql.Identifier('id"field')))

    def setUp(self):
        with psycopg.connect() as conn:
            conn.execute('TRUNCATE dataset, example, link, all_data, "quoted.table" RESTART IDENTITY')
            conn.execute('INSERT INTO dataset(name) VALUES (%s), (%s)', ("O'Reilly reviews", 'other'))
            payload = json.dumps({'text': 'Отличный "товар"', 'meta': {'id': '001'}}, ensure_ascii=False).encode('utf-8')
            conn.execute('INSERT INTO example(content) VALUES (%s), (%s)', (payload, b'{"meta":{}}'))
            conn.execute('INSERT INTO link VALUES (1,1), (1,2)')
            conn.execute('INSERT INTO all_data VALUES (%s,%s,%s),(%s,%s,%s)', ('001', 'used', 'a', '002', 'new', 'b'))
            conn.execute('INSERT INTO "quoted.table" VALUES (%s,%s,%s)', ('UUID:1', 'quoted column', 'c'))

    def test_exact_value_and_utf8(self):
        self.assertEqual(read_annotations("O'Reilly reviews", dataset_id=1)[0]['text'], 'Отличный "товар"')
        for name in ["' OR true --", "'; DROP TABLE dataset; --"]:
            with self.assertRaises(ValueError):
                read_annotations(name, dataset_id=1)
        with psycopg.connect() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM dataset').fetchone()[0], 2)

    def test_unseen_examples_and_null_annotation_id(self):
        rows = read_examples(dataset_name="O'Reilly reviews", table_name='all_data', id_field='id')
        self.assertEqual([r['meta']['id'] for r in rows], ['002'])
        self.assertEqual(rows[0]['meta']['source'], 'b')

    def test_quoted_identifier_and_json_key(self):
        sources = {'custom': {'schema': 'public', 'table': 'quoted.table', 'id_fields': ['id"field']}}
        with patch.dict(os.environ, {'KEDROGY_SOURCES': json.dumps(sources)}):
            rows = read_examples(dataset_name="' OR true --", table_name='custom', id_field='id"field')
        self.assertEqual(rows[0]['meta']['id"field'], 'UUID:1')
        self.assertEqual(rows[0]['text'], 'quoted column')
        self.assertTrue(rows[0]['meta']['_source_id'].startswith('legacy:'))

    def test_source_denied_before_connection(self):
        with patch('mykedro.db_queries.psycopg.connect') as connect:
            for table, field in [('auth_user', 'id'), ('all_data', 'id; SELECT 1')]:
                with self.subTest(table=table, field=field), self.assertRaises(ValueError):
                    read_examples(dataset_name='x', table_name=table, id_field=field)
            connect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
