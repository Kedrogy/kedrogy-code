"""Validate launch inputs against server-owned policy before any side effects."""

import shlex
import unicodedata
from dataclasses import dataclass

from django.conf import settings
from kedrogy_contracts import CONVERSION_VERSION, LEGACY_POLICY, ContractError, normalize_labels


class LaunchConfigError(ValueError):
    """Configuration rejected, with errors suitable for form/API fields."""

    def __init__(self, field: str, message: str):
        self.errors = {field: [message]}
        super().__init__(f"{field}: {message}")


@dataclass(frozen=True)
class LaunchConfig:
    """Resolved configuration containing no credentials or arbitrary command."""

    image: str
    working_dir: str
    pipeline: str
    dataset_name: str
    table_name: str
    id_field: str
    recipe_args: tuple[str, ...]


def checked_text(value: str, field: str) -> str:
    """Reject empty values and control characters in technical settings."""
    if not isinstance(value, str) or not value.strip():
        raise LaunchConfigError(field, "This setting is required.")
    if any(unicodedata.category(char).startswith("C") for char in value):
        raise LaunchConfigError(field, "Control characters are not allowed.")
    return value


def parse_labels(value, *, policy=CONVERSION_VERSION) -> tuple[str, ...]:
    """Parse a bounded, unambiguous list of labels for command/config output."""
    try:
        return normalize_labels(value, policy=policy)
    except ContractError as error:
        raise LaunchConfigError("labels", str(error)) from error


def validate_dataset(data: dict) -> LaunchConfig:
    """Resolve API or persisted dataset data against one approved ML profile."""
    if data.get("binding_state") == "UNRESOLVED":
        raise LaunchConfigError("dataset_name", "Resolve this dataset's Prodigy binding before launching an operation.")
    name = checked_text(data.get("dataset_name"), "dataset_name")
    if name.startswith("-"):
        raise LaunchConfigError("dataset_name", "A dataset name cannot start with '-'.")
    image = checked_text(data.get("image"), "image")
    if image not in settings.KEDROGY_ML_IMAGE_ALIASES:
        raise LaunchConfigError("image", "This image is not in the server's approved image list.")
    working_dir = checked_text(data.get("workingDir"), "workingDir")
    if working_dir != "mykedro":
        raise LaunchConfigError("workingDir", "The approved working directory is 'mykedro'.")
    pipeline = data.get("pipeline") or "load_examples"
    if pipeline != "load_examples":
        raise LaunchConfigError("pipeline", "The approved annotation pipeline is 'load_examples'.")
    table = checked_text(data.get("data_table_name"), "data_table_name")
    field = checked_text(data.get("id_field"), "id_field")
    source = settings.KEDROGY_SOURCES.get(table)
    if not source:
        raise LaunchConfigError("data_table_name", "This source is not approved by the server.")
    if data.get("source_config") is not None and data["source_config"] != source:
        raise LaunchConfigError("data_table_name", "The registered source identity changed. Create a new dataset binding.")
    if field not in source["id_fields"]:
        raise LaunchConfigError("id_field", "This ID column is not approved for the source.")
    options = checked_text(data.get("recipe_options"), "recipe_options")
    try:
        args = shlex.split(options)
    except ValueError as exc:
        raise LaunchConfigError("recipe_options", "Unbalanced quotes in recipe options.") from exc
    policy = data.get("annotation_policy", LEGACY_POLICY)
    if policy not in (LEGACY_POLICY, CONVERSION_VERSION):
        raise LaunchConfigError("annotation_policy", "Unknown annotation policy.")
    recipe = "myrecipes.textcat.choice" if policy == CONVERSION_VERSION else "myrecipes.textcat.custom-model"
    path = "./data/00_examples/examples.jsonl"
    if args and args[0] == recipe:
        if len(args) != 5 or args[2] != path or args[1] not in {name, data.get("display_name", name)}:
            raise LaunchConfigError("recipe_options", "Use '-l positive,negative', or the approved recipe with this dataset name and examples path.")
        args = args[3:]
    if len(args) != 2 or args[0] not in ("-l", "--label"):
        raise LaunchConfigError("recipe_options", "Only '-l label1,label2' is supported.")
    try:
        labels = parse_labels(args[1], policy=policy)
    except LaunchConfigError as exc:
        raise LaunchConfigError("recipe_options", exc.errors["labels"][0]) from exc
    return LaunchConfig(
        image=settings.KEDROGY_ML_IMAGE, working_dir=f"/app/{working_dir}",
        pipeline=pipeline, dataset_name=name, table_name=table, id_field=field,
        recipe_args=(recipe, name, path, "-l", ",".join(labels)),
    )


def validate_preprocessor(value: str) -> str:
    """Restrict entry-point selection to the installed approved implementation."""
    if value not in ("", "a_preprocess_fun"):
        raise LaunchConfigError("a_preprocess_fun", "Use 'a_preprocess_fun', or leave empty for no preprocessing.")
    return value
