"""Validated API contracts for editable drafts and immutable runtime identity."""

import shlex
from typing import ClassVar

from django.db import transaction
from django.db.models import Q
from rest_framework import serializers

from .launch_config import (
    LaunchConfigError,
    checked_text,
    parse_labels,
    validate_dataset,
    validate_preprocessor,
)
from .models import DjangoDataset, DjangoModel


class DjangoDatasetSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(source="dataset_name", required=False, max_length=200)
    dataset_name = serializers.CharField(required=False, max_length=200)
    pending_cleanup = serializers.SerializerMethodField()
    labelled = serializers.SerializerMethodField()
    annotation_data = serializers.SerializerMethodField()
    annotation_session = serializers.SerializerMethodField()
    pipeline = serializers.CharField(allow_blank=True, required=False, default="load_examples")

    def to_internal_value(self, data):
        if "display_name" in data and "dataset_name" in data and data["display_name"] != data["dataset_name"]:
            raise serializers.ValidationError({"display_name": "Conflicting display-name aliases."})
        return super().to_internal_value(data)

    def validate(self, attrs):
        try:
            if "dataset_name" in attrs or not self.instance:
                name = checked_text(attrs.get("dataset_name"), "dataset_name").strip()
                if name.startswith("-"):
                    raise LaunchConfigError("dataset_name", "A display name cannot start with '-'.")
                attrs["dataset_name"] = name
            if not self.instance or set(attrs) - {"dataset_name"}:
                values = self.instance.to_dict() if self.instance else {}
                values.update({k: v for k, v in attrs.items() if k != "dataset_name"})
                if not self.instance:
                    values["dataset_name"] = attrs["dataset_name"]
                    values["annotation_policy"] = "single-label-choice-v2"
                config = validate_dataset(values)
                if "pipeline" in attrs:
                    attrs["pipeline"] = config.pipeline
                if "recipe_options" in attrs:
                    attrs["recipe_options"] = "-l " + shlex.quote(config.recipe_args[-1])
        except LaunchConfigError as exc:
            raise serializers.ValidationError(exc.errors) from exc
        return attrs

    def update(self, instance, validated_data):
        with transaction.atomic():
            current = DjangoDataset.objects.select_for_update().get(pk=instance.pk)
            from .kubernetes import OperationError
            from .operation_control import require_dataset
            require_dataset(current)
            if set(validated_data) - {"dataset_name"} and current.annotation_runs.exclude(status="STOPPED").exists():
                raise OperationError("ANNOTATION_ACTIVE", "Stop annotation before changing its launch configuration.")
            identity_fields = {"data_table_name", "id_field", "recipe_options", "annotation_policy"}
            changes = any(field in validated_data and validated_data[field] != getattr(current, field) for field in identity_fields)
            if changes and (current.source_config is not None or current.binding_state == "BOUND" or current.annotation_runs.exists()):
                raise OperationError("ANNOTATION_IDENTITY_FROZEN", "Create a new dataset to change source identity, classes or annotation policy after annotation has started.")
            return super().update(current, validated_data)

    def get_pending_cleanup(self, obj):
        run = obj.deletion_runs.exclude(status="SUCCEEDED").first()
        return str(run.id) if run else None

    class Meta:
        model = DjangoDataset
        fields: ClassVar[list[str]] = ["annotation_policy", "source_config", "pending_cleanup", "id", "display_name", "dataset_name", "prodigy_dataset_name", "prodigy_dataset_id", "binding_state", "image", "workingDir", "pipeline", "recipe_options", "data_table_name", "id_field", "labelled", "annotation_data", "annotation_session", "deletion_pending", "retired_at", "annotations_deleted"]
        read_only_fields: ClassVar[list[str]] = ["annotation_policy", "source_config", "prodigy_dataset_name", "prodigy_dataset_id", "binding_state", "annotation_data", "annotation_session", "deletion_pending", "retired_at", "annotations_deleted"]

    def get_labelled(self, obj):
        return self.get_annotation_data(obj)["status"] == "PRESENT"

    def get_annotation_data(self, obj):
        from .annotation_data import public_data
        return public_data(obj)

    def get_annotation_session(self, obj):
        from .annotation import public_session
        runs = obj.annotation_runs.all()
        return public_session(next(iter(runs), None))


class LabelsField(serializers.Field):
    def to_representation(self, model):
        try:
            return list(parse_labels(model.label_schema if model.label_schema is not None else model.labels, policy=model.on_dataset.annotation_policy))
        except LaunchConfigError:
            return []

    def to_internal_value(self, value):
        try:
            labels = list(parse_labels(value))
        except LaunchConfigError as exc:
            raise serializers.ValidationError(exc.errors["labels"]) from exc
        return {"label_schema": labels, "labels": ", ".join(labels)[:400]}


class DjangoModelSerializer(serializers.ModelSerializer):
    pending_cleanup = serializers.SerializerMethodField()
    labels = LabelsField(source="*")
    labels_valid = serializers.SerializerMethodField()
    trained = serializers.SerializerMethodField()
    served = serializers.SerializerMethodField()
    serving = serializers.SerializerMethodField()
    last_training_run = serializers.SerializerMethodField()
    a_preprocess_fun = serializers.CharField(allow_blank=True, required=False, default="")
    dataset_name = serializers.CharField(source="on_dataset.dataset_name", read_only=True)

    def get_labels_valid(self, obj):
        return bool(LabelsField().to_representation(obj))

    def get_trained(self, obj):
        return obj.artifact_status == "VERIFIED" and obj.published_run_id is not None

    def get_serving(self, obj):
        from .serving import public_serving
        return public_serving(obj.current_serving)

    def get_served(self, obj):
        return self.get_serving(obj)["status"] == "READY"

    def get_last_training_run(self, obj):
        from .training import public_run
        runs = obj.training_runs.all()
        return public_run(runs[0]) if runs else None

    def validate_a_preprocess_fun(self, value):
        try:
            return validate_preprocessor(value)
        except LaunchConfigError as exc:
            raise serializers.ValidationError(exc.errors["a_preprocess_fun"]) from exc

    def create(self, validated_data):
        with transaction.atomic():
            dataset = DjangoDataset.objects.select_for_update().filter(pk=validated_data["on_dataset"].pk).first()
            if dataset is None:
                raise serializers.ValidationError({"on_dataset": "The dataset was deleted. Select an existing dataset."})
            from .operation_control import require_dataset
            require_dataset(dataset)
            return super().create(validated_data)

    def update(self, instance, validated_data):
        from .kubernetes import OperationError
        with transaction.atomic():
            from .operation_control import require_dataset
            parent = DjangoDataset.objects.select_for_update().get(pk=instance.on_dataset_id)
            require_dataset(parent)
            current = DjangoModel.objects.select_for_update().get(pk=instance.pk)
            if current.resources_deleting or current.retired_at:
                raise OperationError("MODEL_BUSY", "Model resources are being deleted.")
            if "on_dataset" in validated_data and validated_data["on_dataset"].pk != current.on_dataset_id:
                raise serializers.ValidationError({"on_dataset": "Create a new model to use another dataset."})
            return super().update(current, validated_data)

    def get_pending_cleanup(self, obj):
        from .models import DeletionRun
        run = DeletionRun.objects.filter(dataset=obj.on_dataset).exclude(status="SUCCEEDED").filter(
            Q(model=obj) | Q(model__isnull=True)).first()
        return str(run.id) if run else None

    class Meta:
        model = DjangoModel
        fields: ClassVar[list[str]] = ["pending_cleanup", "id", "on_dataset", "model_name", "dataset_name", "labels", "labels_valid", "a_preprocess_fun", "trained", "served", "serving", "artifact_status", "last_training_run", "published_run"]
        read_only_fields: ClassVar[list[str]] = ["trained", "served", "serving", "artifact_status", "last_training_run", "published_run"]
