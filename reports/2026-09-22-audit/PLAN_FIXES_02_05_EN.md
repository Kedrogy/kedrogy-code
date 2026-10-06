# Kedrogy repair plan for findings 02–05

Date: 22 September 2026. Based on the [technical audit](REPORT_EN.md). This is a plan; the application, database and cluster changes had not yet been implemented.

New password login is deferred. These four repairs can be implemented without a login screen. PostgreSQL service passwords, the Django key and build credentials will come automatically from the local environment or Kubernetes Secrets; training and prediction will not require entering them. Finding 01 remains open: fixing injection paths and HTTP methods does not restrict who may use the API.

## Required result

| Finding | Expected behavior |
| --- | --- |
| 02: SQL | User values cannot change query structure; the application runs without superuser privileges. |
| 03: Kubernetes | Input strings cannot add manifest fields; launches require approved configuration and images. |
| 04: secrets | Credentials are absent from source, build context, image layers and regular logs. |
| 05: GET | Opening a link, refreshing a page and polling status do not create tasks or change data. |

## Implementation order

1. Prepare isolated checks and record the working configuration without secret values.
2. Repair finding 05: restrict methods and remove writes from the GET result handler.
3. Repair SQL in finding 02 and prepare minimal PostgreSQL privileges.
4. Repair manifest generation and launch restrictions in finding 03.
5. Complete finding 04: wire Secrets, switch services to prepared roles and verify builds.
6. Run combined checks and record results as an audit supplement.

Findings 03 and 04 are linked: safe manifests must immediately reference secrets instead of embedding values. Role preparation belongs to 02; connection cutover belongs to 04 so services are not left with unusable credentials.

## Preparation and change boundaries

- Inventory images, Kedro/Prodigy parameters, tables and used columns. Build approved configurations from working components; existing rows are not automatically safe.
- Preserve uncommitted user changes. Before changing roles or credentials, verify a usable PostgreSQL backup and recovery route.
- Test SQL on temporary PostgreSQL with synthetic data. Begin manifest checks with generation/parsing, followed by Kubernetes dry-run and dedicated fixtures.
- Use separate test settings and prohibit working-cluster access. AppConfig.ready() currently connects to the database and applies Kubernetes documents; isolate that startup before integration tests. An explicit initialization command is a small dependency on finding 17.
- Verify findings 02–05 specifically. Fixing Prediction failed also requires training results, state and inference work; this plan does not promise that repair.

## 02 Safe SQL and database privileges

Primary locations: [training nodes](../../example/mykedro/src/mykedro/pipelines/train/nodes.py), [example-loading nodes](../../example/mykedro/src/mykedro/pipelines/load_examples/nodes.py), [Kedro catalog](../../example/mykedro/conf/base/catalog.yml).

1. Pass dataset_name separately to execute() in labelled_examples(). Similarly parameterize dataset names and JSON keys in load_examples(). Do not manually replace apostrophes. See [Psycopg parameters](https://www.psycopg.org/psycopg3/docs/basic/params.html).
2. Build schema/table/column names with psycopg.sql.Identifier. Treat schema.table as two validated components. An id_field used as a SQL column needs Identifier; the same value used as a JSON key/path needs a parameter. See [SQL composition](https://www.psycopg.org/psycopg3/docs/api/sql.html).
3. Define a server-controlled source inventory: schema, table, approved ID column and required fields. Correct escaping does not authorize reading every table. Invalid sources must produce field errors before enqueueing.
4. Revalidate before background execution and direct Kedro launches. Stored rows and historical queue parameters cannot bypass restrictions.
5. Replace hardcoded all_data.source with a consistent alias for the selected table. This necessary source-support repair also concerns finding 21. Separate changes to IDs, NOT IN and repeated ingest unless needed for query safety.
6. Prepare separate roles for cutover in step 04. Check existing objects, sequences and future migration objects. Avoid broad grants and unnecessary CREATE in trusted schemas.

| Component | Necessary privileges |
| --- | --- |
| Django and worker | Read/write their application and queue tables, without PostgreSQL administration. |
| Example loading and training | Read approved source tables and annotations; no modification or deletion. |
| Prodigy | Read/write annotation tables and required sequences; prepare the schema separately. |
| Ingest | Write only designated source tables. Existing if_exists: replace requires explicit consideration of table recreation privileges. |
| Migrations and initial setup | Separate administrative connection unavailable to normal tasks. |

Technical roles do not introduce user accounts or passwords into the application UI.

Acceptance: O'Reilly reviews is matched as an exact value; SQL-looking dataset names cannot expand selections or mutate data. Forbidden schemas/tables/columns fail; approved identifiers requiring quoting work. JSON paths cannot inject SQL. Negative tests preserve source tables and rows. Runtime roles have rolsuper=false, readers are denied writes/DDL, and normal annotation/Django operations still work.

## 03 Safe Kubernetes and launch configuration

Primary locations: serializers, tasks and train/serve/prodigy Jinja manifests.

1. Put approved combinations of image, working directory, pipeline, recipe and parameters in server settings. A short list suffices. An approved registry alone is insufficient; pin a verified image digest.
2. Initially retain API fields while validating allowed combinations. PATCH infrastructure fields as strictly as creation. A later UI may select a preset; injection repair does not require rewriting every form.
3. Replace dynamic Jinja interpolation with pure builders and JSON/YAML serialization. Static documents may remain. Serialize nested ConfigMap documents separately; safe outer YAML does not protect a manually assembled inner string.
4. Pass command/args as argument lists. For legacy recipe_options, use shlex.split followed by validation of the recipe, positional values and flags. Parsing alone is not authorization; do not invoke a shell.
5. Stop concatenating arbitrary Kedro strings into --params=...,... . Build a structured configuration file with a fixed schema and mount it in the relevant container. Verify exact preservation of commas, quotes and equals signs.
6. Resolve working directories under the approved image directory; reject parent traversal, unknown paths and control characters in technical fields. Do not impose these restrictions on review text.
7. Derive resource and temporary-file names from server IDs. Replace dataset-name-based prodigy YAML paths with stdin or managed temporary files and guaranteed cleanup.
8. Revalidate stored configuration in the worker before building documents. Reject invalid historical rows with actionable field diagnostics instead of silently repairing or launching them.
9. Scope workload ServiceAccounts and disable automatic API tokens where unnecessary. Independently scope controller/local kubeconfig privileges; changing a Pod account does not constrain a privileged host process. Check privileged, hostPath and hostNetwork requirements; introduce non-root settings only after verifying directory/PVC access.

Use small typed configuration objects and document builders instead of a generic Kubernetes framework. Nested dictionaries are acceptable at the external serialization boundary; business settings should have separate types.

Acceptance: newline/securityContext injection and unapproved images fail before enqueueing/Kubernetes access. Quotes and special characters preserve PodSpec, nested ConfigMap and argument boundaries. Traversal and unsupported recipes/flags fail. Direct worker execution observes the same checks. Label/Train/Serve documents parse and pass server-side dry-run; a permitted fixture container receives the intended arguments, files and volume access.

## 04 Secrets and Docker builds

Primary locations: settings, both Dockerfiles, .dockerignore, mysite.yaml and postgres.yaml.

1. Inventory credential purposes without recording values: Django, PostgreSQL, existing Prodigy access, private packages and registries. Inspect comments, local Kedro configurations and generated files.
2. Keep local values outside Git and Docker. Provide only variable names and safe placeholders in an example. Diagnose missing required settings by name and configuration route; do not use a shared default password.
3. Store Kubernetes credentials separately through secretKeyRef or mounted files. Secret names/keys are server-controlled; passwords do not belong in ConfigMaps. Do not add user password login in this scope.
4. Generate prodigy.json with JSON serialization from environment/mounted settings. Shell-assembled JSON can break on quotes/backslashes; validate every connection setting, including port.
5. Exclude .env variants, nested virtual environments, .git, node_modules, private configurations, local data, archives and generated manifests from every Docker context. Check root and ML builds. Git ignore rules do not untrack already tracked files.
6. Replace COPY . /app with explicit code, package metadata and lockfile copies. Preserve necessary build/licensing files without local credentials.
7. Use BuildKit secret mounts for private-package credentials and SSH mounts when needed. Remove secrets from ARG, persistent ENV, command URLs and logs. See [Docker build secrets](https://docs.docker.com/build/building/secrets/).
8. Remove complete manifest printing from render_print and similar paths. Log operation/resource IDs and safe reasons. Check exception/task metadata for DSN/configuration exposure.
9. Switch to prepared PostgreSQL roles and verify each service before disabling old runtime credentials. Existing-volume passwords must be changed on the database role; changing container environment alone does not rotate them. Coordinate PostgreSQL, Django, worker and Prodigy.
10. Replace active credentials found in source or released artifacts. Removing a current line does not remove Git-history/image copies. Check accessible historical images and identify which were tested. Git rewriting remains a separate decision.

Acceptance: tracked source/templates and environment examples contain no active secrets. Build contexts, image layers, final filesystem, configuration, history and accessible build metadata contain no control secret values. Deleting a file in a later layer is insufficient. Passwords with quotes, backslashes and dollar signs retain exact values. All services run with new connections; service-secret rotation does not require an application rebuild. Missing settings and logs remain safe under control-secret checks.

The missing root pyproject.toml is finding 40. Restore it from the actual workspace and verify the lockfile before declaring the complete root build successful. Otherwise leave image verification explicitly incomplete; context and other-image checks can proceed.

## 05 GET without state changes

Primary locations: views, legacy/root URLs and detail_model.html.

1. Require POST for new_dataset, new_model, label_dataset, delete_dataset, train_model, serve_model and delete_model. A separate read-only GET may show a creation form. Use [require_POST](https://docs.djangoproject.com/en/6.0/topics/http/decorators/).
2. Check every caller and replace launch/delete links with CSRF-protected POST forms. Retain working POST forms.
3. Preserve legacy CSRF and test with actual CSRF enforcement. Do not use csrf_exempt to pass tests. This does not close anonymous REST access in finding 01.
4. Remove update_latest_dataset() from new_dataset_result(). Move pointer updates into successful task completion, transactionally and with retry handling. GET results only read status. A full redesign of labelled in finding 13 is separate.
5. Check other status and GET/HEAD handlers for writes. Invalid methods for model/dataset creation must fail before database/queue access.
6. Cover regular and i18n_patterns legacy routes. Retain React API POST actions and verify GET cannot launch them.

Retain the legacy UI with corrected methods for this change. Removing it is a separate option.

Acceptance: commands return 405 for GET/HEAD without changing row/task counts or calling Kubernetes. Missing-CSRF POST fails; a valid form enqueues one operation for the request. Polling does not change DjangoLastDataset or other tables. Successful tasks update the pointer themselves; failed tasks do not. Regular/localized paths retain read pages and POST buttons.

## Pattern analysis

Problem: validate untrusted configuration and pass it into PostgreSQL, Kubernetes and HTTP handlers with controlled side effects.

- Contracts and errors: Python robustness items 81, 83, 85 and 88; explicit validation, narrow handling and preserved safe causes.
- Typed configuration: classes/interfaces 48, 51 and 56; dictionaries 29. Immutable dataclasses for validated internal settings; DRF for external inputs. Dataclasses/annotations do not themselves validate at runtime.
- Resources: robustness 82 and concurrency 67; context-managed database/temp files, subprocess argument lists and guaranteed cleanup. A complete kubectl redesign belongs to finding 07.
- Integration checks: testing/debugging 109–112; real PostgreSQL for query/privilege semantics and isolated boundaries/autospec for rejecting launches before Kubernetes.
- Configuration/interfaces: collaboration 118, 120, 121 and 124; environment settings, concrete errors, annotations and brief documentation.

Rejected options: a new async/thread layer, metaclasses/custom ORM/generic validation framework, an external login service, SQL regexes as the only protection, and manual YAML escaping. The task concerns correctness and privileges rather than parallel throughput, and login is deferred.

Proposed module structure, not files created by this plan:

```text
example/mykedro/src/mykedro/
  db_queries.py                   # Safe queries, approved sources, SourceSpec
  pipelines/train/nodes.py         # Annotation reads
  pipelines/load_examples/nodes.py # Example reads
kedrogy/src/kedrogy/
  launch_config.py                 # Allowed combinations, LaunchConfig
  manifests.py                    # Pure Kubernetes document builders
  serializers.py                  # External API field errors
  tasks.py                        # Prelaunch checks, execution and results
  views.py                        # Methods, forms and read-only results
mysite/src/mysite/settings.py      # Service configuration
kedrogy/tests/
  test_launch_config.py           # Restrictions and historical records
  test_manifests.py               # Documents and nested parameters
  test_legacy_methods.py          # Methods, CSRF and absence of side effects
example/mykedro/tests/
  test_db_queries.py              # PostgreSQL value boundaries and privileges
```

Public Python functions need annotations/docstrings and explicit package exports; distributed typed packages need py.typed. Do not create a shared library for a few lines. Pass source rules through agreed configuration and validate at execution.

Decisions: dataclasses internally and existing DRF for HTTP; structured serialization; exact server image allowlists; retained legacy routes with corrected methods; real temporary PostgreSQL for SQL/privileges and mocks for proving no task/Kubernetes launch on rejection.

Avoid asserts for user validation, silent broad exception handling, mutated caller dictionaries, mutable defaults, unmanaged connections/files, lost causes and secret-bearing generated reprs. SQL values must be parameters; the readable f-string guidance is not a SQL-safety rule. A template-string test does not establish real query behavior.

Use existing Psycopg 3, Django/DRF and standard dataclasses, json, pathlib, tempfile, shlex and unittest.mock. Declare a safe YAML serializer in the package that imports it. Kubernetes Python SDK is optional.

Guidance: Python Best Practices py-design and its domain guides; SQL PostgreSQL DDL/security rules PG-D15 and PG-D17; E2E security testing on least privilege, secret-free source and negative input checks. General authorization guidance is deferred at the user's request.

## Combined verification and implementation report

Run relevant checks after each block, then approved configuration creation, PostgreSQL data access, annotation and Train/Serve preparation in isolation. Broken model #20 is not the sole acceptance criterion.

The report must identify changed files, actual test results and switched services. Classify each finding as fixed, partially fixed or unverified against its acceptance criteria. Finding 01 and the rest of the audit are not automatically closed.
