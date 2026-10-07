# GitHub migration and contribution audit

Completed on 7 October 2026, using the Europe/Moscow client date.

## Migration result

- Source: https://github.com/wildfluss/kedrogy-code
- Destination: https://github.com/Kedrogy/kedrogy-code
- Destination repository ID: 1407944003; private, matching source visibility.
- Copied every published branch and tag: 7 branches, 13 tags, 105 reachable commits.
- Preserved the default branch, main. Branches were copied separately; their code was not merged into main.
- No issues, pull requests, discussions, repository secrets, variables, or other service metadata were imported.
- Issue and wiki features are disabled on the new repository. GitHub Actions was temporarily disabled during historical tag pushes to prevent package publishing; availability was restored afterward.
- The old Kedrogy URL redirected to wildfluss before repository creation. The destination now resolves to a separate repository.

## Verified authorship correction

The user confirmed ownership of millafedotova and millapsina. All 17 personal commits in the published source history used the Git author name millafedotova and email fedotovamilla@gmail.com. GitHub associated that email with millapsina. It was therefore not sufficient to change the displayed Git author name or add a name-only mailmap.

Only the personal email in author and committer headers was changed to 144226851+millafedotova@users.noreply.github.com, using the authenticated primary account ID 144226851. Author names were preserved. The GitHub API independently confirmed millafedotova as the author of all 17 corrected commits.

- Corrected author email: 17 commits.
- Corrected personal committer email: 11 commits.
- Preserved the team-ysz committer on 6 personal commits originally applied by that contributor.
- Preserved authors and committers on every other commit: 88 other-author commits.
- Preserved every author date, committer date, and timezone exactly.
- Preserved every tree, file blob, commit message, and co-author trailer exactly.
- Preserved the parent graph under the old/new commit mapping.
- 24 commit hashes changed: 17 personal commits and 7 descendant commits whose parent references changed. The descendant commits retain their original authorship, timestamps, messages, and file contents.

GitHub's documented account association and noreply-address format: [commit email settings](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address), [email address reference](https://docs.github.com/en/account-and-profile/reference/email-addresses-reference).

## Relationship to the thesis project plan

The plan reviewed was docs/thesis/kedrogy_detailed_thesis_project_plan.md, alongside docs/thesis/kedrogy_thesis_verification_checklist.md. Both are currently local, uncommitted files. The plan explicitly describes later periods as reconstructed estimates. It does not provide exact historical completion dates.

Dates were not invented or moved to match the plan. The following distinctions must remain visible in thesis evidence:

| Plan activity | Planned or estimated months in 2026 | Published Git evidence and limits |
| --- | --- | --- |
| Interface and translations | February | Personal translation and interface commits begin on 19 February. Further UI work appears in March. |
| React SPA | February–March | eedad70 created the SPA on 25 February; 1920725 added styling on the same day; f8f3a00 added application pages on 2 March. |
| Dataset and model pages | March–April | f8f3a00 added pages on 2 March; 54d5230 revised pages on 16 March; 9422cdc updated components on 18 April. |
| Django REST API | March–April | 54d5230 records API work on 16 March; e8e1481 records backend work on 28 March; c43cbf6 adds dedicated API files on 18 April. |
| React and API integration | April–May | Source history shows integration work already on 16 March and 18 April. The copied history contains no personal May commit. |
| Prodigy integration | May–June | Core Prodigy infrastructure already exists in other contributors' January–February commits. Examples include cfde10a, 7edd40e, 2bd60ea and 39b9d9f. Personal later application integration must be distinguished from those foundations. No personal May–June commit establishes the reconstructed completion period. |
| Annotation workflow | June–July | No published personal June–July commit in this source snapshot confirms the period. A later application integration claim requires other contemporaneous evidence. |
| Training and prediction | July–August | Other contributors' training and prediction foundations predate this period. Personal application controls appear in March–April; no personal July–August commit confirms later refinement dates. |
| Workflow checks | August–September | No published personal August–September commit confirms these checks. Local reports and test logs are separate evidence and were not imported as historical commits. |
| Technical documentation | September–October | The local thesis documents are uncommitted and are not part of the source repository's published Git history. Their existence does not establish earlier implementation dates. |

The published personal commit dates end on 18 April 2026. Absence of a later commit does not establish that no later work happened; it limits what this source Git history proves. The plan and checklist were not edited.

## Personal commits

The original author dates below were preserved, including timezone offsets.

| Original SHA | Destination SHA | Original and preserved author date | Subject |
| --- | --- | --- | --- |
| [b6ac336](https://github.com/wildfluss/kedrogy-code/commit/b6ac33677c55cc6c694e6838bad1c619f0fbee3b) | [7768424](https://github.com/Kedrogy/kedrogy-code/commit/7768424ab3a8306a77e164cb4777db5c757b6ea8) | 2026-02-19T17:18:13+03:00 | kedro translations |
| [0beb254](https://github.com/wildfluss/kedrogy-code/commit/0beb254357858524113aad720e7a54cfa48b6bf6) | [8ac379a](https://github.com/Kedrogy/kedrogy-code/commit/8ac379ae3da0c0f5f575fa15c527b031928b43f2) | 2026-02-19T17:37:33+03:00 | translations fixed |
| [a2256cc](https://github.com/wildfluss/kedrogy-code/commit/a2256cc1f008a5b5e2a37c5d5b50aa125df4039e) | [db16770](https://github.com/Kedrogy/kedrogy-code/commit/db1677092ad7e50379c29d01833f444d0f8fb619) | 2026-02-25T17:31:44+03:00 | translations done fixes #3 |
| [d208914](https://github.com/wildfluss/kedrogy-code/commit/d208914f3b922d1ade8a454fc98edf20080b0710) | [ed73cac](https://github.com/Kedrogy/kedrogy-code/commit/ed73cacdf52c2baf3a03cd745ce8d1c2948fe186) | 2026-02-21T23:29:33+03:00 | daisy ui added |
| [663a4d5](https://github.com/wildfluss/kedrogy-code/commit/663a4d5eca432b62692455ede77f0ef6be2bd942) | [772c6ec](https://github.com/Kedrogy/kedrogy-code/commit/772c6ec5dd15ea269c370b9c4318e989db7ac459) | 2026-02-22T21:30:50+03:00 | button added |
| [ce9dddc](https://github.com/wildfluss/kedrogy-code/commit/ce9dddc5e58249876dacef3452d9cf750ac7cb2d) | [2bf0c4f](https://github.com/Kedrogy/kedrogy-code/commit/2bf0c4fd884464422676ff6d42716378ed3f5fc6) | 2026-02-25T18:22:15+03:00 | index.html fixed |
| [bf68935](https://github.com/wildfluss/kedrogy-code/commit/bf68935ca8b581125b18bc4932e8f14571fe6693) | [5658ffc](https://github.com/Kedrogy/kedrogy-code/commit/5658ffcd026aa409f758580ded149c81037a00f4) | 2026-03-03T23:18:53+03:00 | fixed #8 |
| [65b486b](https://github.com/wildfluss/kedrogy-code/commit/65b486b7e417d51c95dbdf4d74fd1f8e669f4ff3) | [9fb70ef](https://github.com/Kedrogy/kedrogy-code/commit/9fb70ef2cf252e72d3982a798bdb49d9e133522f) | 2026-03-06T00:38:19+03:00 | datasets field fixed |
| [3364db9](https://github.com/wildfluss/kedrogy-code/commit/3364db9c64027f6ad8e7400cce9fad673ad35d68) | [1c9b1a4](https://github.com/Kedrogy/kedrogy-code/commit/1c9b1a4f90b40b0282b69e84560f0682e7c4edc1) | 2026-03-13T00:52:12+03:00 | daisy ui fixed & added |
| [6462ff0](https://github.com/wildfluss/kedrogy-code/commit/6462ff0ce36c28f4cf2523d965c0567676f701ed) | [eeb84df](https://github.com/Kedrogy/kedrogy-code/commit/eeb84df90d5692f54c337d3b0e7c1589cc98088c) | 2026-03-14T13:45:45+03:00 | fixed ui |
| [eedad70](https://github.com/wildfluss/kedrogy-code/commit/eedad702b20f1d225415aeb561b5cb7cd07122be) | [62ee222](https://github.com/Kedrogy/kedrogy-code/commit/62ee222b9d508ae883d5f1f31c9f7451dd249ff7) | 2026-02-25T19:15:16+03:00 | base for spa created |
| [1920725](https://github.com/wildfluss/kedrogy-code/commit/1920725c7ea80cf2f60acd94d92ae4e08790b8fe) | [7a87301](https://github.com/Kedrogy/kedrogy-code/commit/7a87301e7d1d3d96cfbc60ff910fc2c78f8501dd) | 2026-02-25T19:30:48+03:00 | daisyui and tailwind added |
| [f8f3a00](https://github.com/wildfluss/kedrogy-code/commit/f8f3a00f2a8967f6c915759e2d02af5a1a4af279) | [d9beefe](https://github.com/Kedrogy/kedrogy-code/commit/d9beefe6f45dcef6fa0583ec339d5e1be6ca127f) | 2026-03-02T18:39:36+03:00 | app pages added |
| [54d5230](https://github.com/wildfluss/kedrogy-code/commit/54d52307ac19470b6146ea53a9574e568376d57d) | [2aa96fd](https://github.com/Kedrogy/kedrogy-code/commit/2aa96fdcb82aded54b202cf92463302ef5651553) | 2026-03-16T21:58:04+03:00 | rest api added with claude |
| [e8e1481](https://github.com/wildfluss/kedrogy-code/commit/e8e1481ca681296fc0dd5654e9a957094ff02ef2) | [5939285](https://github.com/Kedrogy/kedrogy-code/commit/5939285b2bab702d9cb12c86d1a0128ee243add7) | 2026-03-28T22:34:46+03:00 | backend added |
| [9422cdc](https://github.com/wildfluss/kedrogy-code/commit/9422cdc43aaa18f2089be0cd2cec354a524f2e0f) | [e9e4edc](https://github.com/Kedrogy/kedrogy-code/commit/e9e4edc9fd362e1b07162b42fdbd6b05e4cf54eb) | 2026-04-18T20:40:31+02:00 | Add DaisyUI components matching Figma, wire API to Django backend |
| [c43cbf6](https://github.com/wildfluss/kedrogy-code/commit/c43cbf6f1ba38dc1ee0c458e1c17e57ea8f3a0d0) | [491e7f9](https://github.com/Kedrogy/kedrogy-code/commit/491e7f9a4ba6b9929cfeca2802a9d756e1c0a0cd) | 2026-04-18T20:41:22+02:00 | Add Django REST API for React SPA integration |

## Verification and recovery artifacts

- verification.json: metadata checks and the complete mapping for all 105 commits and 20 branch/tag refs.
- github-attribution.json: GitHub API evidence for each of the 17 corrected authors.
- commit-map.tsv: machine-readable original/destination commit map.
- source-refs.tsv: original published branch/tag inventory.
- original-history.bundle: self-contained original Git history. git bundle verify confirmed completeness and integrity.

A fresh clone downloaded from the destination was checked independently: exactly 105 reachable commits and 20 branch/tag refs, all commit bytes matching the authorized email and parent substitutions, and git fsck passing. Every source and destination file tree matches under the mapping.

## Local workspace boundary

The active local checkout was not reset, rebased, cleaned, staged, or committed. Existing uncommitted code, documents, and the local-only bcfde46 commit were not pushed because the requested source was the published GitHub repository. This report and its recovery artifacts are new local files only.

The local origin already points to Kedrogy/kedrogy-code, while the local branches and cached tracking refs still contain the pre-correction history. Use a fresh clone for the corrected history and retain this dirty checkout while preserving or transferring its pending work.

The source repository and its refs remain unchanged. Existing source collaboration metadata remains there.
