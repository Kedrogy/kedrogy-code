# Company-mention model repair

## Confirmed cause

Model 23 previously had 20 accepted examples (7 company mentions and 13 negatives). Its training split contained only 15 examples. With a batch size of 16 and one epoch, the classifier received one optimizer update. The saved checkpoint achieved 20% validation accuracy and returned `company_mentioned` for all six diagnostic probes.

Checkpoint verification checked identity, hashes, class mapping, loading and a finite forward pass. It did not establish classification quality. The interface also retained the previous prediction when input was edited or cleared.

## Changes

- Training defaults now use eight epochs, batch size eight, learning rate 0.00003 and a maximum sequence length of 256. Settings are validated and their effective values are frozen in each training run. Explicit short runs remain available for infrastructure smoke tests and are flagged in the quality report.
- The random seed is applied before the classification head is initialized. Checkpoint selection uses macro F1, rather than validation loss alone.
- Identical normalized texts are deduplicated before splitting. Conflicting labels for the same text stop training. The stratified split remains reproducible.
- Each new checkpoint includes a hashed `quality.json` with validation accuracy, macro F1, majority-class baseline, class support, predicted class counts, confusion matrix and optimizer step count. A compact summary appears in training history. Missing predicted classes, failure to beat the majority baseline, small validation sets and very short training runs produce explicit warnings.
- The interface distinguishes checkpoint integrity from validation quality. Historical checkpoints without recorded metrics are shown as unassessed. Validation is explicitly described as checkpoint-selection data, not an independent test.
- Editing input clears the old prediction and cancels its request. A late response cannot overwrite a newer request. Model/serving changes and unmounts invalidate pending predictions. Requests have a timeout and visible loading feedback.

## Annotation provenance

156 AI-assisted, headline-only annotations were appended through the installed Prodigy API to the existing dataset 24. The resulting 176 unique texts contain 40 `company_mentioned` and 136 `no_company` answers. All source rows and prior answers were preserved. Exact duplicate headlines were excluded from the additions.

The label definition is an explicitly named commercial company or brand. A generic mention of a company, a person, a government agency, a place or a sports team alone is negative. Labels are a demo annotation set and have not received independent human adjudication.

The source remains the existing English news corpus. There are no Russian training examples. Cross-language performance must be measured separately and should not be inferred from the multilingual base model's name.

## Evaluation protocol

The saved training/validation split contains 132 training and 44 validation examples. `independent-cases.json` was written before inspecting the retrained model's results. It contains 16 English and 8 Russian diagnostic cases, including named companies, generic company references and ordinary non-business sentences. These texts are not imported into Prodigy or used for training/checkpoint selection. They form a small diagnostic suite, not a representative production benchmark.

## Runtime results

- New training run: `1e029920-eb90-4277-8800-e4ab379fb75f`.
- New serving revision: `34b23cab-c281-47a7-a383-e5ef423ffaea`, confirmed READY through the application API.
- The run completed 136 optimizer updates over eight epochs. Macro F1 selected checkpoint 68 (epoch four); later epochs did not improve this metric. The published weights are that selected checkpoint, not the final optimizer state.
- Validation: 41/44 correct (93.18%), macro F1 0.8993, majority baseline 77.27%. In class order `company_mentioned`, `no_company`, the confusion matrix is `[[8, 2], [1, 33]]`.
- Independent diagnostic suite: 23/24 correct, comprising 16/16 English and 7/8 Russian. The saved API results match the read-only candidate evaluation for every case.
- Six original failure probes: 5/6 correct, compared with 3/6 previously. The dog, weather and Russian cat examples now correctly return `no_company`; Microsoft examples return `company_mentioned`. The Tesla example is a false negative.
- Combined diagnostic checks: 28/30 correct. The remaining errors are `Tesla opened a new factory.` and the Russian Sberbank branch-opening case in [independent-cases.json](independent-cases.json), both predicted as `no_company`. The original multilingual inputs are preserved in the data; these failures were not added to training or hardcoded into inference.

The constant-output failure is resolved. This small English news model still has generalization errors, especially on company names and language/domain coverage absent from its training data. The diagnostic score is not a production accuracy estimate. Broader independently reviewed multilingual data and a larger untouched test set are needed before relying on unrestricted inputs.

## Verification

- Frontend build passed; 26 frontend contract, localization and request-race tests passed.
- 35 focused Django training/operation tests passed, including immutable defaults, valid quality receipts and rejection of nonfinite metrics.
- Four training-quality/split tests and six real offline artifact tests passed.
- Browser checks confirmed that clearing text removes its old prediction, editing during an outstanding request cancels its visible result, and the page observes the new serving revision.
- Existing source data, previous annotations, historical checkpoint files and other models were retained. The previous model 23 serving revision was stopped using the application's normal workflow.

## Evidence files

- `annotation-summary.json`, `annotations.jsonl`: saved annotation provenance and class counts.
- `training-start.json`, `trained-artifact.json`, `release-image.json`: immutable training configuration, quality report, selected checkpoint and image identity.
- `candidate-evaluation.json`, `api-evaluation.json`: separate diagnostic cases before and after serving.
- `original-probes-after.json`: exact original failure queries, with before/after results.
- `serving-start.json`, `previous-serving.json`: serving revision change.
