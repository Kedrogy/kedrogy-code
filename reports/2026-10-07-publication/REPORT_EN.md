# Repository publication verification

Date: 7 October 2026. Destination: Kedrogy/kedrogy-code. Branch: codex/integrate-lifecycle-workflow.

This publication collects the pending application, annotation, training, inference, lifecycle, deployment, tests, reports and thesis-document changes. It builds on the migrated history and preserves the local UI commit through an equivalent commit with the migrated parent and primary account email. Its original dates and file tree remain unchanged. The earlier local branch retains the original commit as a recovery point.

## Language review

The user explicitly retained Russian localization and multilingual data while requiring English code, comments, documentation, commit messages and GitHub content.

- Translated five September audit/repair documents into English, retaining all 47 audit findings, their priorities, evidence limits and code-location references. Updated links to the English filenames. Local originals remain under ignored .local/english-publication-backup-20261007.
- Python AST/token checks found no Cyrillic identifiers, comments or docstrings. TypeScript/JavaScript AST/comment checks likewise found none; Cyrillic regex ranges used to verify localization are data expressions.
- Remaining Cyrillic source literals belong to interface translations and multilingual fixtures. JSON/JSONL evaluation inputs and localized screenshots are retained as data.
- Markdown prose is English. The company-evaluation report references the original Russian test case in its JSON evidence rather than repeating it in documentation.
- Word XML was inspected. The manuscript was already English. Nineteen localized style display names in the project plan were translated without changing style IDs, formatting or any other document member. Its four rendered pages were visually reviewed.
- The frozen thesis evidence ZIP contains Cyrillic only in four localization source files, matching the authorized exception. The archive and its recorded checksum were preserved.

## Verification

| Check | Result |
| --- | --- |
| Backend on disposable PostgreSQL 14.20 | 128 tests passed, no skips. |
| ML/data on a separate disposable PostgreSQL database | 40 tests passed, no skips. |
| Frontend contracts and localization | 26 tests passed, no skips. |
| TypeScript/Vite production build | Passed. |
| Django migration drift | No changes detected. |
| git diff --check | Passed for the existing diff; repeated after staging all files. |
| Common GitHub/AWS/private-key credential patterns | No matches in candidate text files; this is a scoped pattern check, not proof that every possible secret is absent. |

The complete current total is 194 successful tests. PostgreSQL used a dedicated temporary cluster under /private/tmp with Unix-socket-only access and separate backend/source databases. These checks did not access the working project database or Kubernetes. This current run used PostgreSQL 14.20; historical PostgreSQL 18 evidence remains separately dated in earlier reports.

One regression fixture needed adjustment: the catalog round-trip/split test previously supplied identical text with conflicting labels. The current training splitter correctly rejects those inputs. That test now supplies distinct texts and still checks class representation in both partitions and disjoint row indices. The annotation identity tests continue to retain their original identical-text fixtures.

ESLint remains an unavailable gate: npm run lint fails because app/eslint.config.js/mjs/cjs is missing. This publication does not claim lint success or a new live Kubernetes/browser acceptance run.

## Recovery artifacts

The original migration bundle is retained locally and excluded through the *.bundle ignore rule. Private environments, credentials, generated builds and virtual environments remain ignored. The commit includes the migration report/mapping and project evidence, but does not embed a duplicate Git-history bundle.

The archived migration report describes the migration-time state. This publication report records the subsequent commit/PR preparation and current verification.
