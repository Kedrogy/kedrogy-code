# Training quality and checkpoint integrity

A verified checkpoint has a valid immutable identity, expected class mapping, checked file hashes and a working offline forward pass. Verification does not guarantee accurate predictions.

New training runs save `quality.json` inside their checkpoint. The artifact manifest contains its hash and a compact summary for the API and training history. Metrics are computed on the stratified validation split after loading the checkpoint selected by macro F1. They must not be described as independent test results. Review class coverage, macro F1 and the majority-class baseline together with accuracy.

Warnings identify missing predicted classes, accuracy that does not exceed the majority baseline, fewer than ten validation examples for any class and fewer than ten optimizer steps. Warnings are diagnostic, not an automatic deployment gate; operators should evaluate candidate models on separate representative examples before replacing a working serving revision. Historical artifacts without metrics remain compatible and are explicitly unassessed.

## Configuration

`KEDROGY_TRAIN_OPTIONS` accepts a JSON object with the following settings. Defaults are resolved and saved in the immutable run snapshot before the job is created.

| Setting | Default | Accepted values |
| --- | --- | --- |
| `num_train_epochs` | 8 | Integer, 1–50 |
| `learning_rate` | 0.00003 | Finite number, 0.0000001–0.001 |
| `train_batch_size` | 8 | Integer, 1–64 |
| `eval_batch_size` | 16 | Integer, 1–64 |
| `max_length` | 256 | Integer, 16–512 |
| `weight_decay` | 0.01 | Finite number, 0–1 |
| `seed`, `data_seed` | 123 | Integer, 0–4294967295 |
| `max_steps` | -1 | -1 uses epochs; 1–100000 overrides epochs |
| `base_model` | `bert-base-multilingual-uncased` | Nonempty offline model name or path |

Use short `max_steps` overrides only for infrastructure tests. They do not demonstrate model quality. Hyperparameter defaults are a starting point; data volume, annotation consistency, language coverage and independent evaluation still determine whether a model is useful.

Identical texts, normalized for case and whitespace, are deduplicated before splitting to prevent direct leakage. Conflicting labels for identical normalized texts stop training. The random seed is set before initializing the classifier head.
