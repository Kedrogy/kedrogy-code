"""Validated, reproducible training options shared by launchers and ML workers."""

import math

DEFAULTS = {
    "seed": 123, "data_seed": 123, "num_train_epochs": 8,
    "learning_rate": 3e-5, "train_batch_size": 8, "eval_batch_size": 16,
    "max_length": 256, "weight_decay": 0.01, "max_steps": -1,
    "base_model": "bert-base-multilingual-uncased",
}


def training_options(overrides: dict) -> dict:
    """Reject malformed options before a training Job consumes resources."""
    if not isinstance(overrides, dict) or set(overrides) - DEFAULTS.keys():
        raise ValueError("Training options contain unsupported settings.")
    options = DEFAULTS | overrides
    limits = {"seed": (0, 2**32 - 1), "data_seed": (0, 2**32 - 1),
              "num_train_epochs": (1, 50), "train_batch_size": (1, 64),
              "eval_batch_size": (1, 64), "max_length": (16, 512)}
    for key, (low, high) in limits.items():
        if type(options[key]) is not int or not low <= options[key] <= high:
            raise ValueError(f"Invalid training option: {key}.")
    for key, low, high in [("learning_rate", 1e-7, 1e-3), ("weight_decay", 0, 1)]:
        value = options[key]
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"Invalid training option: {key}.")
    if type(options["max_steps"]) is not int or not (options["max_steps"] == -1 or 1 <= options["max_steps"] <= 100000):
        raise ValueError("Invalid training option: max_steps.")
    if not isinstance(options["base_model"], str) or not options["base_model"].strip():
        raise ValueError("Invalid training option: base_model.")
    return options
