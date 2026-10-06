# Kedrogy implementation results for findings 02–05

Date: 22 September 2026. Changes were applied to the working project, local environment and k3d cluster. The original [plan](PLAN_FIXES_02_05_EN.md) and [audit](REPORT_EN.md) are retained. Password login was not added. Service credentials are supplied automatically; Label, Train and Serve do not require password entry.

| Finding | Result |
| --- | --- |
| 02: SQL and database privileges | Fixed: query parameters are separate from SQL, sources are restricted and runtime connections use dedicated PostgreSQL roles instead of a superuser. |
| 03: launch parameters and Kubernetes | Fixed for new launches: structured documents, a server-controlled profile, worker revalidation, a pinned ML image and scoped privileges. Historical Serve resources were not automatically migrated. |
| 04: secrets and images | Partially fixed: current code and new images were cleaned; local PostgreSQL and Django secrets were replaced. Active external-index credentials were found in two historical images; provider-side rotation remains necessary. |
| 05: mutating GET requests | Fixed: commands require POST, HTML forms use CSRF and result polling does not write data. |

This result covers these four findings. The remaining findings in the 47-item audit are not declared resolved. Model #20's `Prediction failed` error needs separate checkpoint, training-lifecycle and status work.

## 02 SQL and PostgreSQL

Queries moved to [db_queries.py](../../example/mykedro/src/mykedro/db_queries.py). Dataset names, JSON keys and JSON paths use Psycopg parameters. Schema, table and column identifiers use `sql.Identifier`, after validating the source and ID column against server-side `KEDROGY_SOURCES`. The default permits only `public.all_data` with column `id`.

The train and load_examples nodes use these functions. The hardcoded `all_data.source` reference was removed. Related selection defects were also fixed: JSON stored as bytea is decoded as UTF-8, missing annotation IDs do not block the entire selection, and string IDs retain leading zeros. Annotated rows are excluded through `NOT EXISTS`.

| Role | Purpose and privileges |
| --- | --- |
| `kedrogy_app` | Django and task queue: read/write application tables, without superuser or DDL. |
| `kedrogy_reader` | Example loading and training: read approved sources and annotations. |
| `kedrogy_annotator` | Prodigy: DML on annotation tables and required sequences, without schema creation. |
| `kedrogy_ingest` | Owner of all_data; the existing table-replacing ingest needs DDL. |
| `kedrogy_migrator` | Owner of Django tables with a separate migration connection. |

All five roles have NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOREPLICATION and NOBYPASSRLS. PUBLIC no longer has CREATE on public. Sequence grants and default privileges cover later migration and ingest objects. [configure_database.py](../../scripts/configure_database.py) handles setup and rotation without overwriting an existing recovery-credential directory.

Installed Prodigy attempts `CREATE TABLE IF NOT EXISTS` even when the schema exists; PostgreSQL still requires CREATE. Instead of increasing annotation privileges, the new kedrogy_postgresql adapter verifies prepared tables and uses Prodigy's regular data layer. Initial schema creation uses a separate setup connection. Entry-point registration and real annotation operations were verified in a temporary database.

## 03 Task launch

[launch_config.py](../../kedrogy/src/kedrogy/launch_config.py) validates image, working directory, pipeline, recipe, labels, source, ID field and preprocessing. Serializers, API/legacy commands and the worker apply validation; the worker rereads the current database record. An old queue payload cannot replace launch settings.

The server accepts exact approved-image aliases and substitutes KEDROGY_ML_IMAGE, currently the verified ML image digest. Arbitrary images, newlines in technical fields, parent-directory traversal, another recipe or extra flags fail before Kubernetes access. Approved settings include workingDir=mykedro, annotation pipeline load_examples, recipe myrecipes.textcat.custom-model, a fixed example path and validated labels. Preprocessing permits the installed a_preprocess_fun or an empty value.

Dynamic Jinja templates were replaced by [manifests.py](../../kedrogy/src/kedrogy/manifests.py). Kubernetes and nested Kedro parameters are built as data structures and serialized as JSON. Commands use argument lists without a shell. Quotes, colons and Unicode in permitted data cannot become PodSpec fields or shell arguments.

New workloads use a separate ServiceAccount without an automatic API token, RuntimeDefault seccomp, allowPrivilegeEscalation=false, privileged=false and capabilities.drop=[ALL]. Training receives the reader secret. Inference receives no PostgreSQL credentials and mounts artifacts read-only. runAsNonRoot is not enabled; compatibility with a non-root UID needs separate verification.

The controller has a namespace-scoped Role without Secret reads or RBAC writes. Local Django and workers use a separate scoped kubeconfig; the personal kubectl context was unchanged. This limits application privileges and does not establish a complete admission policy against a compromised controller.

The kubectl wrapper checks exit codes, bounds waiting and omits complete manifests/stderr from task metadata. Label/Serve succeed only after rollout; Train waits for Job completion. A full lifecycle, repeated training and cleanup redesign remains outside findings 02–05.

## 04 Secrets, builds and service cutover

Hardcoded Django keys, old password-bearing Prodigy/SQLAlchemy configurations and secrets in templates/examples were removed. Required settings come from the environment; missing settings are diagnosed by name. [.env.example](../../.env.example) contains no active credentials. Git and Docker exclude local .env, .local/credentials and kubeconfig files. Credential files use mode 0600.

Kubernetes uses secretKeyRef rather than plaintext ConfigMap/Deployment passwords. Secrets are published through stdin without last-applied annotations containing values. prodigy.json is generated with JSON serialization, includes the required port, uses mode 0600 and lives on a memory-backed volume. Tests covered quotes, backslashes and dollar signs in passwords.

Both Dockerfiles use explicit COPY instructions and BuildKit secret mounts for private indexes; secret ARG/ENV values were removed. .dockerignore excludes local environments, .git, .env variants, node_modules, private configurations and data. Root workspace/lock metadata, package metadata and dependencies were repaired for complete builds. The Hugging Face Xet download path returned 404 and was disabled; the regular model download succeeded during the build.

Images were built and published only to the project's local registry:

| Image | Final digest | Audit result |
| --- | --- | --- |
| mysite:security-20260922-final | sha256:7f93427dca9701bd597ddf0ab2396514580df62d813a28924065cc981f4054cc | 15 layers, 20,926 files, no matches for control secret values. |
| mykedro:security-20260922-final | sha256:e972019b2cb4d1f1573f5f6002ab70ace61688b6eaf56312c332cd3b2d00eae5 | 20 layers, 50,981 files, no matches for control secret values. |

[audit_image.py](../../scripts/audit_image.py) checks all layers, configuration and metadata for private paths and known long secret values. It does not prove the absence of unknown secrets; short common passwords are unsuitable for reliable byte searches. Results: [image-security-checks.json](image-security-checks.json).

Two accessible historical images were also checked. kedrogy-registry.localhost:5500/mykedro:latest contained the current UV_INDEX_PRODIGY_USERNAME value; lts-registry.localhost:5500/mykedro:latest also contained UV_INDEX_YSZ_PASSWORD. This project supplies the Prodigy credential as the private-index username. Values are omitted. Paths are listed in [historical-image-checks.json](historical-image-checks.json).

Finding 04 cannot be fully closed before these external credentials are reissued. Deleting a local image does not revoke a provider credential. Management access was not established, and the user was asked who owns the credentials. Git history, historical images and model volumes were not rewritten or removed during this work.

The working environment received these changes:

- PostgreSQL and Django secrets were replaced. The old exposed PostgreSQL password was rejected; the new administrative password worked.
- Django and workers switched to kedrogy_app and restarted. Frontend and both list APIs returned HTTP 200. The checked counts were three datasets and two models.
- Prodigy switched to the new ML digest and kedrogy_annotator; its loader uses kedrogy_reader. The Deployment was ready and returned HTTP 200 after cutover and after PostgreSQL restart.
- PostgreSQL uses a Secret; old plaintext fields and the saved annotation were removed. The persistent volume was retained.
- The old fixed Prodigy Basic Auth configuration was removed to retain local access without a user password.
- The local backend remains the running server. A complete Kubernetes backend Deployment in mysite.yaml was prepared but not launched alongside it.

## 05 HTTP methods and read-only polling

new_dataset, new_model, label_dataset, delete_dataset, train_model, serve_model and delete_model require POST. GET/HEAD return 405 before queue or Kubernetes access. Django Serve/Delete links became CSRF-protected POST forms.

new_dataset_result no longer changes DjangoLastDataset. Successful Label completion writes the pointer transactionally under a PostgreSQL advisory lock; retries do not create duplicates. A failed rollout does not update it. The separate finding concerning the meaning of “last dataset = labelled” was not fully redesigned.

Database and Kubernetes access were removed from AppConfig.ready(), allowing safe import and isolated testing. Static assets are installed explicitly.

## Checks actually performed

| Check | Result and scope |
| --- | --- |
| Django regressions | 10 tests passed locally and in the final backend image: GET/HEAD on regular, /en/ and /ru/ paths; CSRF; read-only polling; worker/API revalidation; safe kubectl errors. |
| Real temporary PostgreSQL 18 | Four tests passed: apostrophes/SQL payloads, UTF-8, quoted identifiers/JSON keys, string IDs, NULL annotations and rejecting forbidden sources before connection. |
| Secret JSON generation | Two tests passed: exact special-character preservation, file permissions and missing-setting diagnostics. |
| PostgreSQL roles | Synthetic database checks covered reader DDL/write denial, application DML, migrator/ingest object creation and runtime non-superuser status. |
| Prodigy | Real CRUD under the scoped annotator role and plugin entry-point loading passed, including the final ML image. Working HTTP returned 200 after cutover. |
| Kubernetes | Label/Train/Serve documents passed server-side dry-run with the scoped controller kubeconfig. Deployment creation was permitted; Secret reads and ClusterRoleBinding creation were denied. |
| Real workload containers | A temporary Train Job read its ConfigMap, connected as reader and wrote a synthetic artifact to a new PVC. The Serve PodSpec container read it, received EROFS on write, and had neither PG credentials nor an API token. Train effective capabilities were zero. Verification Python replaced expensive ML commands, so training itself was not tested. Job, ConfigMap and PVC were removed afterward. |
| New images | Both builds succeeded; all layers and configuration were scanned for known secret values and private paths. |
| Static checks and dependencies | Ruff passed for new/reworked modules and tests; git diff --check and uv lock --check --offline passed. |

Mutating database tests used synthetic data, Django migrations and the schema created by installed Prodigy. Final workload verification also connected read-only to the working database without printing rows. Automatic approval review rejected a working database export and then a schema-only transfer because they copied user data or structural metadata. Neither operation was performed or bypassed. A usable working database backup was not verified, a deviation from the plan's preparation step. Roles were tested separately before cutover, and new credentials were saved locally before changes were committed. Working rows were neither exported nor replaced by fixtures.

## Next launch and remaining work

- The application is at http://localhost:5173 and backend at http://127.0.0.1:8000. [SECURITY_SETUP.md](../../SECURITY_SETUP.md) documents startup, rotation and tests.
- The local controller token was requested for 24 hours. Refresh it with scripts/refresh_kubeconfig.py before a later demonstration; this does not introduce a UI password.
- Dataset #19's full recipe refers to test3 although its name differs. A new launch returns a clear error; existing annotations were not reassigned. Active Prodigy continues the earlier annotation session.
- Model #20 was not retrained and its missing checkpoint was not restored. Historical trained/served flags and preprocessing_fun values were not changed in bulk. Build and dry-run success do not prove model quality or successful end-to-end training.
- Historical Serve Deployments, Jobs and PVCs were not deleted or migrated in bulk. Unready resources remain; cleanup and lifecycle repair need separate work.
- API authorization remains deferred, as do the duplicate URL namespace warning and other audit findings.
- Closing finding 04 requires provider-side revocation/replacement of exposed Prodigy/YSZ credentials and updating the private build environment. Their values are absent from reports and regular logs.

Python, SQL and E2E testing guidance informed explicit validation, structured parameters, context-managed resources, separate runtime/setup privileges, negative checks and real PostgreSQL query verification. UX controls guidance informed HTML actions. Pre-existing user changes were preserved; no commit or remote Git publication was performed during this implementation task.
