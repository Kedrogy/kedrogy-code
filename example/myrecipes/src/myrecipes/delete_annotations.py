"""Delete one verified annotation dataset without cascading into session datasets."""

import argparse
import hashlib
import json
import os
from contextlib import closing
from pathlib import Path

import psycopg2


def digest(rows):
    h = hashlib.sha256()
    for identifier, content in rows:
        h.update(str(identifier).encode() + b":" + hashlib.sha256(bytes(content)).digest())
    return h.hexdigest()


def delete_bound_dataset(connection, name, identifier, fingerprint):
    """Bounded table locks exclude concurrent Prodigy writes during this transaction."""
    with connection, connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout = '5s'")
        cursor.execute("SET LOCAL statement_timeout = '30s'")
        cursor.execute("LOCK TABLE public.dataset, public.link, public.example IN SHARE ROW EXCLUSIVE MODE")
        cursor.execute("SELECT id, session, meta FROM public.dataset WHERE name=%s", (name,))
        row = cursor.fetchone()
        if row is None:
            cursor.execute("SELECT 1 FROM public.dataset WHERE id=%s", (identifier,))
            if cursor.fetchone():
                raise ValueError("ANNOTATION_IDENTITY_CHANGED")
            return
        meta = json.loads(bytes(row[2])) if row[2] is not None else {}
        if row[:2] != (identifier, False) or not isinstance(meta, dict) or meta.get("structured", False):
            raise ValueError("ANNOTATION_IDENTITY_CHANGED")
        cursor.execute("SELECT e.id,e.content FROM public.link l JOIN public.example e ON e.id=l.example_id WHERE l.dataset_id=%s ORDER BY e.id", (identifier,))
        rows = cursor.fetchall()
        if digest(rows) != fingerprint:
            raise ValueError("ANNOTATIONS_CHANGED")
        ids = list({row[0] for row in rows})
        cursor.execute("DELETE FROM public.link WHERE dataset_id=%s", (identifier,))
        cursor.execute("DELETE FROM public.dataset WHERE id=%s AND name=%s", (identifier, name))
        # Only newly unreferenced examples from this exact dataset are removed.
        # Shared examples and associated session datasets remain intact.
        cursor.execute("DELETE FROM public.example e WHERE e.id=ANY(%s) AND NOT EXISTS (SELECT 1 FROM public.link l WHERE l.example_id=e.id)", (ids,))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name")
    parser.add_argument("identifier", type=int)
    parser.add_argument("fingerprint")
    args = parser.parse_args()
    try:
        with closing(psycopg2.connect(connect_timeout=5)) as connection:
            delete_bound_dataset(connection, args.name, args.identifier, args.fingerprint)
    except (ValueError, psycopg2.Error):
        result = {"error": {"code": "ANNOTATION_DELETE_FAILED", "message": "Annotation cleanup failed or its reviewed data changed. Review the operation before retrying."}}
        Path(os.environ.get("KEDROGY_TERMINATION_LOG", "/dev/termination-log")).write_text(json.dumps(result))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
