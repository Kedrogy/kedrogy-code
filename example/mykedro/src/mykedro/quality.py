"""Report validation quality separately from checkpoint integrity."""

from sklearn.metrics import accuracy_score, confusion_matrix, f1_score


def quality_report(targets, predictions, *, classes: int, training_steps: int, train_samples: int) -> dict:
    """Include class coverage and a majority baseline; small holdouts need review."""
    if len(targets) != len(predictions) or not len(targets):
        raise ValueError("Validation requires aligned, nonempty targets and predictions.")
    if any(int(value) != value or not 0 <= value < classes for value in [*targets, *predictions]):
        raise ValueError("Validation labels are outside the configured class mapping.")
    matrix = confusion_matrix(targets, predictions, labels=list(range(classes)))
    support = matrix.sum(axis=1).tolist()
    predicted = matrix.sum(axis=0).tolist()
    accuracy = float(accuracy_score(targets, predictions))
    baseline = max(support) / len(targets)
    warnings = []
    if any(count == 0 for count in predicted):
        warnings.append("missing_predicted_classes")
    if accuracy <= baseline:
        warnings.append("not_above_majority_baseline")
    if min(support) < 10:
        warnings.append("small_validation_sample")
    if training_steps < 10:
        warnings.append("few_training_steps")
    return {"version": 1, "split": "validation", "samples": len(targets),
            "train_samples": train_samples, "training_steps": training_steps,
            "accuracy": accuracy, "macro_f1": float(f1_score(targets, predictions, labels=list(range(classes)), average="macro", zero_division=0)),
            "majority_baseline": baseline, "support": support, "predicted_counts": predicted,
            "confusion_matrix": matrix.tolist(), "warnings": warnings}
