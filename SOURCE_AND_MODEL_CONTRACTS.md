# Source imports and classification contracts

New source imports are append-only. New annotation datasets use explicit single-label choices. Historical source tables, annotations and verified v1 artifacts retain their original identities and semantics.

## Register and import a source

Use an existing database administrator connection to run the source-only setup. It does not create or rotate passwords. Without `--apply`, setup prints the intended schema/grant changes. The `kedrogy_migrator`, `kedrogy_ingest`, `kedrogy_reader` and `kedrogy_app` roles must already exist.

```sh
mysite/.venv/bin/python scripts/configure_sources.py --create-source product-reviews-v2
mysite/.venv/bin/python scripts/configure_sources.py --create-source product-reviews-v2 --apply
```

The setup returns a source UUID. Add it to the server-owned `KEDROGY_SOURCES` registry, preserving any existing approved entries:

```json
{
  "product_reviews_v2": {
    "schema": "kedrogy_source",
    "table": "record",
    "id_fields": ["id"],
    "source_id": "<source UUID returned by setup>"
  }
}
```

Restart the API and reconcilers after changing their environment. The dataset API receives the approved registry key (`product_reviews_v2`), never an arbitrary SQL table. A dataset's source configuration, ID field, annotation policy and class schema become immutable when annotation begins.

Run imports with the existing ingest credentials in standard `PG*` environment variables. Do not put passwords in command arguments or repository files. The examples below start from the repository root:

```sh
example/.venv/bin/python -m mykedro.sources reviews.jsonl \
  --source product-reviews-v2 --request-key import-2026-09-26

example/.venv/bin/python -m mykedro.sources reviews.jsonl \
  --source product-reviews-v2 --request-key import-2026-09-26 --apply
```

The first command is a dry run. The second commits records and the import receipt atomically. After a connection failure, retry with the same request key and unchanged input to recover the same receipt. Reordering the input does not change its fingerprint. A subset import retains all earlier records. Reusing a key with different input or changing an existing record's text/provenance fails the entire transaction.

CSV and JSONL require `text` and an explicit string `id`, plus optional `meta` (a JSON object) and `source` provenance. Leading zeros remain significant. JSON numeric IDs are rejected rather than coerced. Example:

```json
{"id":"001","text":"An excellent product.","source":"review-export","meta":{"language":"en"}}
```

Files without upstream IDs require a separately registered source using `--identity-policy content-addressed-v1`. That mode hashes exact text and provenance. It cannot distinguish identical occurrences; duplicate identities fail unless `--deduplicate` explicitly collapses identical records and records the count. Correcting an existing record requires a new source namespace/version. Imports are limited to 64 MiB, 100,000 records, 60,000 UTF-8 bytes per text and 16,384 bytes per metadata object.

Generic `kedro run` performs no import. The explicit `ingest` pipeline uses the same adapter and requires `source_key` and `request_key` parameters; its default is a dry run. No `SQLTableDataset` output replaces the source table.

## Historical sources and annotations

Source setup transfers `public.all_data` ownership to the migrator and keeps its rows unchanged. Runtime roles cannot write or drop it. Managed-source runtime ingest privileges are SELECT/INSERT only; schema ownership remains with the migrator.

With reader credentials, preview an approved legacy source without exporting its texts or copying its rows:

```sh
example/.venv/bin/python scripts/preview_legacy_source.py --source all_data --id-field id
```

The preview counts missing IDs, duplicate IDs and empty texts. Unique old IDs do not prove they were stable upstream identifiers. Any later copy must retain original source/ID provenance and explicitly select a new source namespace. Existing annotations stay attached to their original binding.

With the backend's existing private environment loaded, preview a legacy annotation binding:

```sh
mysite/.venv/bin/python -m django preview_annotation_policy 20 \
  --labels '["positive","negative"]' --settings=mysite.settings_local
```

The numeric argument is a dataset ID, not a model ID. This command reports counts only and never changes answers. Exact accepted labels can be reviewed for reuse; rejected suggestions require reannotation. `P`/`N` aliases are never inferred. There is no automatic historical conversion command: create a new binding with provenance or reannotate after selecting the intended mapping.

## Explicit annotation and training

For a new dataset, configure at least two distinct classes. The approved `myrecipes.textcat.choice` recipe displays all classes. Select exactly one and press Accept. Reject and Ignore/Skip supply no training target. `OTHER` exists only when explicitly configured and selected as a normal class. Source plus record identity defines an example; identical text in different records is retained.

Training preflight and the training worker share one conversion implementation. Both validate accepted choices, provenance, duplicate/conflicting answers, fingerprint and class support. Training requires at least four distinct accepted records and at least two per class. A bounded ordered class schema is validated before Kubernetes work starts. This prevents data with insufficient support from failing only during the stratified split.

| Contract | Legacy | New default |
| --- | --- | --- |
| Annotation policy | `reject-other-v1`; new training blocked for review | `single-label-choice-v2` |
| Artifact/class-schema version | 1 | 2 |
| Class IDs | `[OTHER, ...configured labels]` | Configured labels at `0..N-1` |
| HTTP envelope version | 1 | 1; explicit `class_schema_version: 2` |
| Existing verified checkpoints | Read and predict with their original mapping | Read and predict with their stored explicit mapping |

Unknown or inconsistent version/policy combinations fail validation. A verified legacy checkpoint is not relabeled, retrained or promoted merely because the new software is installed. Invalid historical artifacts remain invalid.

## Serving ownership and controller cutover

New ServingRuns use `run-owned-v2`: an immutable saved resource plan, per-run Deployment and Service names, an immutable ConfigMap anchor, exact owner UIDs and the actual namespace UID. A matching name or label is insufficient for adoption or deletion. Missing/replaced resources return a conflict or loss error; use a reviewed Stop/new Serve operation to create a new revision.

Prediction follows the current READY run's saved Service and verifies the serving/training/class identities again after inference. Stop immediately invalidates eligibility and the worker lease generation. Terminal tombstones collect delayed old creates while preserving newer and unrelated resources. The reconciler must remain running for eventual cleanup.

During a release, pause lifecycle submissions and stop every old API/worker/reconciler process, including worker descendants. `scripts/run_local.py worker` now terminates the child process group on shutdown. Apply additive migrations, install source grants, deploy digest-pinned compatible images, refresh scoped Kubernetes access and restart the new controllers exclusively. Namespace identity inspection requires GET on the exact configured namespace, with no namespace mutation rights.

Historical fixed-name serving resources remain `legacy-fixed-v1`. Missing historical UIDs require manual ownership review; the new controller does not infer ownership from old names. Authentication remains a separate deferred feature.

## Rollback

Before any v2 records are written, additive Django migrations can be reversed in a disposable validation environment. After v2 records, artifacts or managed imports exist, keep their schema and history. Use a release that understands both versions, or stop affected operations and roll forward. Do not start an old controller against new resource plans or restore destructive ingestion privileges. Source setup is deliberately separate from the password-rotation helper.
