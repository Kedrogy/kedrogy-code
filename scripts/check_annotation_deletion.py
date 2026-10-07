"""Verify scoped annotation deletion against disposable PostgreSQL and shared links."""
import json
import os
from pathlib import Path
from contextlib import closing

env = json.loads(Path('.local/lifecycle-env.json').read_text())
if env.get('KEDROGY_TEST_DATABASE') != 'disposable' or env['PGDATABASE'] != 'lifecycle':
    raise RuntimeError('Disposable lifecycle database required.')
os.environ.update(env)
from prodigy.components.db import connect
from prodigy.util import set_hashes
import psycopg2
from myrecipes.delete_annotations import delete_bound_dataset, digest

db = connect('postgresql', {k:env[v] for k,v in [('host','PGHOST'),('port','PGPORT'),('dbname','PGDATABASE'),('user','PGUSER'),('password','PGPASSWORD')]})
with psycopg2.connect() as setup:
    with setup.cursor() as c:
        c.execute('TRUNCATE public.dataset, public.example RESTART IDENTITY CASCADE')
for name in ['delete-parent','keep-parent','keep-session']:
    db.add_dataset(name, session=name.endswith('session'))
shared = set_hashes({'text':'Shared synthetic example','label':'P','answer':'accept'})
unique = set_hashes({'text':'Unique synthetic example','label':'N','answer':'reject'})
db.add_examples([shared], datasets=['delete-parent','keep-parent','keep-session'])
db.add_examples([unique], datasets=['delete-parent'])
with closing(psycopg2.connect()) as connection:
    with connection.cursor() as c:
        c.execute('SELECT id FROM dataset WHERE name=%s',('delete-parent',)); identifier=c.fetchone()[0]
        c.execute('SELECT e.id,e.content FROM link l JOIN example e ON e.id=l.example_id WHERE l.dataset_id=%s ORDER BY e.id',(identifier,)); rows=c.fetchall()
        expected=digest(rows)
    try:
        delete_bound_dataset(connection,'delete-parent',identifier,'wrong-fingerprint')
    except ValueError:
        pass
    else:
        raise AssertionError('Changed data was deleted.')
    delete_bound_dataset(connection,'delete-parent',identifier,expected)
    delete_bound_dataset(connection,'delete-parent',identifier,expected)
    with connection.cursor() as c:
        c.execute("SELECT name FROM dataset WHERE name IN ('delete-parent','keep-parent','keep-session') ORDER BY name")
        assert c.fetchall()==[('keep-parent',),('keep-session',)]
        c.execute("SELECT count(*) FROM link l JOIN dataset d ON d.id=l.dataset_id WHERE d.name IN ('keep-parent','keep-session')")
        assert c.fetchone()[0]==2
        c.execute('SELECT count(*) FROM example WHERE id=ANY(%s)',([r[0] for r in rows],))
        assert c.fetchone()[0]==1
        c.execute("CREATE TABLE all_data(id serial PRIMARY KEY,text text,source text)")
        c.executemany('INSERT INTO all_data(text,source) VALUES (%s,%s)', [('good product','synthetic'),('bad product','synthetic'),('excellent product','synthetic'),('poor product','synthetic'),('fine product','synthetic')])
    connection.commit()
print('Shared examples and session datasets preserved; fingerprint refusal, idempotent replay, and unreferenced-example removal passed.')
