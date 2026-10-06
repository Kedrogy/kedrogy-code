# Constant company-mention predictions

## Findings

Model 23 (`news-company-mentions-classifier`) returned `company_mentioned` for all six diagnostic requests sent directly to the application's prediction API. The probes included English and Russian sentences with named companies and sentences without companies. This reproduces the main problem independently of the React interface.

The API responses consistently identify training run `a1ff21ec-af00-4e24-a541-c67b643b4d7f` and serving run `ee9bc275-9d93-478d-bd5f-37d8ece2637b`. Class mappings in the saved checkpoint are correct: class 0 is `company_mentioned`, class 1 is `no_company`. No serving preprocessor is configured.

The checkpoint uses a full-size BERT architecture: 12 layers, hidden size 768, and vocabulary size 105879. It is not the tiny architecture used in isolated infrastructure tests.

## Training evidence

- The annotation snapshot contains 20 accepted examples: 7 company mentions and 13 examples without a company.
- The training pipeline holds out 5 examples, leaving 15 for training.
- Training hardcodes one epoch and a batch size of 16.
- The saved Trainer state confirms `global_step=1`, `max_steps=1`, and `num_train_epochs=1`. This single step follows from the dataset size and training settings; the active server training options are empty.
- Recorded validation accuracy is 0.2 on the five-example holdout, with validation loss approximately 0.7025. This is a very small evaluation set and does not establish generalization quality.

These observations support insufficient task-specific training as the primary cause. The six probes do not establish that every possible input produces the same class.

The 20 examples were demonstration annotations prepared earlier in this session. Passing preflight establishes valid labels and minimum class support, not a useful classifier.

## Separate application issues

1. Model verification checks checkpoint integrity, identity, label mappings and offline loading. It does not enforce a predictive-quality threshold; a low-quality classifier can be published and served successfully.
2. The prediction page retains its previous result when the text input changes or is cleared. A late response is also not tied to the currently displayed input. The empty input with a visible answer in the screenshot is consistent with this UI state bug.

## Remediation scope

Expand and review task-specific annotations, make training duration configurable, evaluate both classes on a separate held-out sample, and expose quality metrics separately from artifact verification. Bind each displayed prediction to its submitted text and serving revision, and hide or invalidate it when either changes.

No model was retrained, replaced, stopped or deleted during this investigation. Application source files were not changed. Evidence is recorded in `api-probes.json` and `training-diagnostics.json`.
