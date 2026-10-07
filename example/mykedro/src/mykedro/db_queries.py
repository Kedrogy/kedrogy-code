"""Read approved sources using bound values and quoted SQL identifiers."""

import json
import os
import uuid
from dataclasses import dataclass

import psycopg
from psycopg import sql


@dataclass(frozen=True)
class SourceSpec:
    """A server-approved table and ID column."""

    schema: str
    table: str
    id_field: str
    source_id: str | None = None


def source_spec(table_name: str, id_field: str) -> SourceSpec:
    """Resolve a source from trusted environment configuration."""
    sources = json.loads(os.environ.get(
        "KEDROGY_SOURCES", '{"all_data":{"schema":"public","table":"all_data","id_fields":["id"]}}'
    ))
    entry = sources.get(table_name)
    if not entry or id_field not in entry["id_fields"]:
        raise ValueError("Source table or ID column is not permitted.")
    source_id = entry.get("source_id")
    if source_id is not None:
        source_id = str(uuid.UUID(source_id))
        if (entry["schema"], entry["table"], id_field) != ("kedrogy_source", "record", "id"):
            raise ValueError("Managed sources must use the approved source record schema.")
    return SourceSpec(entry["schema"], entry["table"], id_field, source_id)


def read_annotations(dataset_name: str, *, dataset_id: int, limit: int = 100000) -> list[dict]:
    """Read one consistent annotation snapshot and verify the stable identity."""
    with psycopg.connect(options="-c default_transaction_read_only=on -c statement_timeout=15000") as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        if conn.execute("SELECT id FROM public.dataset WHERE name=%s AND session IS NOT TRUE", (dataset_name,)).fetchall() != [(dataset_id,)]:
            raise ValueError("The annotation dataset identity changed after preflight.")
        rows = conn.execute("""
            SELECT convert_from(e.content, 'UTF8')::jsonb
            FROM public.link AS l JOIN public.example AS e ON e.id = l.example_id
            WHERE l.dataset_id = %s ORDER BY e.id LIMIT %s
        """, (dataset_id, limit + 1)).fetchall()
    if len(rows) > limit:
        raise ValueError("The annotation limit was exceeded.")
    return [row[0] for row in rows]


def read_examples(*, dataset_name: str, table_name: str, id_field: str) -> list[dict]:
    """Read five unseen examples without interpreting input as SQL."""
    source = source_spec(table_name, id_field)
    if source.source_id is not None:
        with psycopg.connect(options="-c default_transaction_read_only=on -c statement_timeout=15000") as conn:
            rows = conn.execute("""
                SELECT jsonb_build_object('text', r.text, 'meta', jsonb_build_object(
                    'id', r.id, '_record_id', r.id, '_source_id', r.source_id,
                    '_content_digest', r.content_digest, '_identity_policy', c.identity_policy,
                    'source', r.provenance->'source'))
                FROM kedrogy_source.record r JOIN kedrogy_source.collection c ON c.id=r.source_id
                WHERE r.source_id=%s AND NOT EXISTS (
                    SELECT 1 FROM public.link l JOIN public.dataset d ON d.id=l.dataset_id
                    JOIN public.example e ON e.id=l.example_id
                    WHERE d.name=%s AND convert_from(e.content,'UTF8')::jsonb #>> '{meta,_source_id}'=r.source_id::text
                    AND convert_from(e.content,'UTF8')::jsonb #>> '{meta,_record_id}'=r.id::text)
                ORDER BY r.id LIMIT 100000
            """, (source.source_id, dataset_name)).fetchall()
        return [row[0] for row in rows]
    query = sql.SQL("""
        SELECT jsonb_build_object(
            'text', src.text,
            'meta', jsonb_build_object(%s::text, src.{id}, 'source', src.source)
        )
        FROM {table} AS src
        WHERE src.text IS NOT NULL AND src.{id} IS NOT NULL
        AND NOT EXISTS (
            SELECT 1
            FROM public.link AS l
            JOIN public.dataset AS d ON d.id = l.dataset_id
            JOIN public.example AS e ON e.id = l.example_id
            WHERE d.name = %s
            AND convert_from(e.content, 'UTF8')::jsonb #>> %s::text[] = src.{id}::text
        )
        ORDER BY src.{id}
        LIMIT 5
    """).format(id=sql.Identifier(source.id_field), table=sql.Identifier(source.schema, source.table))
    with psycopg.connect() as conn, conn.cursor() as cur:
        cur.execute(query, (id_field, dataset_name, ["meta", id_field]))
        result = [row[0] for row in cur.fetchall()]
    from mykedro.sources import fingerprint
    for row in result:
        meta = row["meta"]
        meta.update(_source_id=f"legacy:{source.schema}.{source.table}:{source.id_field}",
                    _record_id=str(meta[id_field]), _content_digest=fingerprint({"text": row["text"], "source": meta["source"]}),
                    _identity_policy="legacy-preserved-v1")
    return result
