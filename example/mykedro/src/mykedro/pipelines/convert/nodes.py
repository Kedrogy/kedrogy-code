"""Preserve explicit upstream identities and exact text during conversion."""

import json

import pandas as pd


def convert(rows) -> pd.DataFrame:
    records = []
    for row in rows:
        meta = dict(row.get("meta", {}))
        if "source" in row:
            meta["source"] = row["source"]
        identifier = row.get("id", meta.get("id"))
        if identifier is not None and not isinstance(identifier, str):
            raise ValueError("Source IDs must be strings; numeric coercion can lose leading zeros.")
        records.append({"id": identifier or "", "text": row["text"],
                        "meta": json.dumps(meta, ensure_ascii=False, sort_keys=True)})
    return pd.DataFrame.from_records(records, columns=["id", "text", "meta"])
