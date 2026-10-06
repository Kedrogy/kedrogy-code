# Fresh demonstration datasets and model records

The old active model/dataset records were retired through cleanup. Exact remaining legacy resources for model #19 and the old Prodigy deployment for `test3` were removed after dependency review. Source texts and saved historical annotations were retained.

The available source contains English news headlines, so the three new tasks use that data rather than inventing reviews or support tickets.

| Dataset | Dataset ID | Model ID | Explicit classes | Accepted examples |
| --- | ---: | ---: | --- | ---: |
| news-sentiment-demo | 22 | 21 | positive, negative, neutral | 20 |
| news-topic-demo | 23 | 22 | business, technology, politics, society | 20 |
| news-company-mentions-demo | 24 | 23 | company_mentioned, no_company | 20 |

## Annotation method

Twenty source headlines were reviewed for each task, producing 60 annotations. The same source sample is used across tasks. Ambiguous headlines with source IDs 13 and 17 were excluded; IDs 27 and 28 provide clearer examples.

- Sentiment: failure, conflict and harm are negative; opportunity, expansion and improvement are positive; descriptive headlines without clear valence are neutral.
- Topic: classify the headline's main focus. Company operations and investment are business; technical systems are technology; elections, government and political commentary are politics; education, workplace culture, migration and sport are society.
- Company mentions: choose `company_mentioned` only for an explicitly named commercial company or brand. A person, place, government agency or sports team alone does not qualify.

The first five sentiment examples were labeled and saved in Chrome. The remaining 55 answers were saved through the installed Prodigy database API using the project's explicit-choice recipe and stable source provenance. Existing answers were checked for conflicts before insertion. JSONL files in this directory contain the saved records for inspection.

All three datasets have unique, verified Prodigy bindings. Every dataset contains exactly 20 accepted records and zero invalid answers. The actual training preflight passes for all three model records, including at least two examples per configured class. These are headline-only demonstration annotations made by Codex.

The model records are ready for training; training and model serving were not started as part of this reset. A managed Prodigy session is available for continuing the company-mention task. The browser did not request a password, so no login credential was entered.

See `final-verification.json` for the active inventory and unchanged-source check, and `annotation-import.json` for class counts and import totals.

## Browser verification

Chrome loaded the new company-mention Prodigy session with `TOTAL 20`, the expected two class choices and the next unseen source record. The application home page was opened in its existing Chrome tab; Prodigy remains in the adjacent tab for continued annotation.
