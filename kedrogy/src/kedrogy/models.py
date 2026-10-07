import uuid
from typing import ClassVar

from django.db import models


def new_annotation_key():
    return f"dataset-{uuid.uuid4()}"


class DjangoDataset(models.Model):
    # column name: dataset_name
    dataset_name = models.CharField(max_length=200)
    prodigy_dataset_name = models.CharField(max_length=200, null=True, unique=True, default=new_annotation_key)
    prodigy_dataset_id = models.PositiveBigIntegerField(null=True, unique=True)
    binding_state = models.CharField(max_length=16, default="PENDING")
    retired_at = models.DateTimeField(null=True, blank=True)
    deletion_pending = models.BooleanField(default=False)
    annotations_deleted = models.BooleanField(default=False)
    source_config = models.JSONField(null=True, blank=True)
    annotation_policy = models.CharField(max_length=32, default="single-label-choice-v2")
    annotation_data = models.JSONField(default=dict)
    annotation_observed_at = models.DateTimeField(null=True)
    annotation_refresh_requested = models.BooleanField(default=True)

    class Meta:
        constraints: ClassVar[list] = [models.CheckConstraint(
            condition=(models.Q(binding_state="UNRESOLVED", prodigy_dataset_name__isnull=True, prodigy_dataset_id__isnull=True)
                       | models.Q(binding_state="PENDING", prodigy_dataset_name__isnull=False, prodigy_dataset_id__isnull=True)
                       | models.Q(binding_state="BOUND", prodigy_dataset_name__isnull=False, prodigy_dataset_id__isnull=False)),
            name="valid_annotation_binding")]

    @property
    def display_name(self):
        return self.dataset_name

    # N/A=migrations
    image = models.CharField(max_length=400, default="N/A")
    workingDir = models.CharField(max_length=200, default="N/A")
    pipeline = models.CharField(max_length=200, default="N/A")
    # recipe = models.CharField(max_length=200, default="N/A")
    recipe_options = models.CharField(max_length=400, default="N/A")
    # parameters for load_examples
    data_table_name = models.CharField(max_length=400, default="N/A")
    id_field = models.CharField(max_length=400, default="N/A")

    def __str__(self):
        return self.dataset_name

    def to_dict(self):
        # print("dataset_id", self.id, flush=True)
        return {
            "dataset_name": self.prodigy_dataset_name,
            "display_name": self.dataset_name,
            "binding_state": self.binding_state,
            "source_config": self.source_config,
            "annotation_policy": self.annotation_policy,
            "prodigy_dataset_id": self.prodigy_dataset_id,
            "image": self.image,
            "workingDir": self.workingDir,
            "pipeline": self.pipeline,
            # "recipe": self.recipe,
            "recipe_options": self.recipe_options,
            # for tasks
            "dataset_id": self.id,
            # parameters for load_examples
            "data_table_name": self.data_table_name,
            "id_field": self.id_field,
        }


class DjangoModel(models.Model):
    on_dataset = models.ForeignKey(
        DjangoDataset,
        on_delete=models.PROTECT,
    )
    model_name = models.CharField(max_length=200, default="", blank=True)
    labels = models.CharField(max_length=400, default="N/A")
    label_schema = models.JSONField(null=True, blank=True)
    resources_deleting = models.BooleanField(default=False)
    legacy_cleanup_review = models.JSONField(default=dict, editable=False)
    retired_at = models.DateTimeField(null=True, blank=True)
    a_preprocess_fun = models.CharField(max_length=400, default="N/A")
    trained = models.BooleanField(default=False)
    served = models.BooleanField(default=False)
    published_run = models.ForeignKey(
        "TrainingRun", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    artifact_status = models.CharField(max_length=16, default="UNVERIFIED")
    current_serving = models.ForeignKey("ServingRun", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    # def __str__(self):
    #     return self.dataset_name


# latest dataset for which prodigy is deployed
class DjangoLastDataset(models.Model):
    dataset = models.ForeignKey(DjangoDataset, on_delete=models.CASCADE)


class TrainingRun(models.Model):
    """One immutable training configuration and its observed execution result."""

    class Status(models.TextChoices):
        QUEUED = "QUEUED"
        RUNNING = "RUNNING"
        VERIFYING = "VERIFYING"
        SUCCEEDED = "SUCCEEDED"
        FAILED = "FAILED"
        TIMED_OUT = "TIMED_OUT"
        INTERRUPTED = "INTERRUPTED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    model = models.ForeignKey(DjangoModel, on_delete=models.PROTECT, related_name="training_runs")
    artifact_removed_at = models.DateTimeField(null=True)
    idempotency_key = models.CharField(max_length=128)
    status = models.CharField(max_length=16, choices=Status, default=Status.QUEUED)
    snapshot = models.JSONField(default=dict)
    task_id = models.CharField(max_length=64, blank=True)
    namespace = models.CharField(max_length=63)
    job_name = models.CharField(max_length=63, unique=True)
    job_uid = models.CharField(max_length=64, blank=True)
    attempts = models.JSONField(default=list)
    artifact = models.JSONField(default=dict)
    error = models.JSONField(default=dict)
    public_logs = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)
    heartbeat_at = models.DateTimeField(null=True)
    lease_owner = models.UUIDField(null=True)
    lease_until = models.DateTimeField(null=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        constraints: ClassVar[list] = [
            models.UniqueConstraint(fields=["model", "idempotency_key"], name="unique_training_request"),
            models.UniqueConstraint(
                fields=["model"], condition=models.Q(status__in=["QUEUED", "RUNNING", "VERIFYING"]),
                name="one_active_training_run",
            ),
        ]


class ServingRun(models.Model):
    """A pinned serving revision, separate from its one-time startup outcome."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    resource_layout = models.CharField(max_length=24, default="legacy-fixed-v1")
    resource_plan = models.JSONField(default=dict)
    lease_epoch = models.PositiveBigIntegerField(default=0)
    cleanup_observed_at = models.DateTimeField(null=True)
    model = models.ForeignKey(DjangoModel, on_delete=models.PROTECT, related_name="serving_runs")
    training_run = models.ForeignKey(TrainingRun, on_delete=models.PROTECT, related_name="serving_runs")
    idempotency_key = models.CharField(max_length=128)
    snapshot = models.JSONField(default=dict)
    namespace = models.CharField(max_length=63)
    deployment_uid = models.CharField(max_length=64, blank=True)
    generation = models.PositiveBigIntegerField(default=0)
    status = models.CharField(max_length=16, default="STARTING")
    startup_status = models.CharField(max_length=16, default="RUNNING")
    error = models.JSONField(default=dict)
    startup_error = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    activated_at = models.DateTimeField(null=True)
    observed_at = models.DateTimeField(null=True)
    stopped_at = models.DateTimeField(null=True)
    lease_owner = models.UUIDField(null=True)
    lease_until = models.DateTimeField(null=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        constraints: ClassVar[list] = [
            models.UniqueConstraint(fields=["model", "idempotency_key"], name="unique_serving_request"),
            models.CheckConstraint(condition=models.Q(resource_layout__in=["legacy-fixed-v1", "run-owned-v2"]), name="valid_serving_layout"),
            models.UniqueConstraint(fields=["model"], condition=models.Q(status__in=["STARTING", "READY", "UNAVAILABLE", "STOPPING"]), name="one_live_serving_run"),
            models.CheckConstraint(condition=models.Q(status__in=["STARTING", "READY", "UNAVAILABLE", "FAILED", "STOPPING", "STOPPED"]), name="valid_serving_status"),
            models.CheckConstraint(condition=models.Q(startup_status__in=["RUNNING", "SUCCEEDED", "FAILED"]), name="valid_serving_startup_status"),
        ]


class AnnotationRun(models.Model):
    """One annotation startup and its independently observed runtime health."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dataset = models.ForeignKey(DjangoDataset, on_delete=models.PROTECT, related_name="annotation_runs")
    namespace = models.CharField(max_length=63)
    idempotency_key = models.CharField(max_length=128)
    snapshot = models.JSONField(default=dict)
    resources = models.JSONField(default=list)
    task_id = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=16, default="STARTING")
    startup_status = models.CharField(max_length=16, default="RUNNING")
    startup_error = models.JSONField(default=dict)
    error = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    observed_at = models.DateTimeField(null=True)
    stopped_at = models.DateTimeField(null=True)
    lease_owner = models.UUIDField(null=True)
    lease_until = models.DateTimeField(null=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        constraints: ClassVar[list] = [
            models.UniqueConstraint(fields=["dataset", "idempotency_key"], name="unique_annotation_request"),
            models.CheckConstraint(condition=models.Q(status__in=["STARTING", "READY", "UNAVAILABLE", "STOPPING", "STOPPED"]), name="valid_annotation_status"),
            models.CheckConstraint(condition=models.Q(startup_status__in=["RUNNING", "SUCCEEDED", "FAILED"]), name="valid_annotation_startup"),
        ]


class AnnotationSlot(models.Model):
    """The namespace slot remains reserved until its previous Pods are gone."""

    namespace = models.CharField(max_length=63, primary_key=True)
    run = models.OneToOneField(AnnotationRun, null=True, on_delete=models.PROTECT, related_name="slot")


class DeletionRun(models.Model):
    """A reviewed cleanup intent whose progress survives worker failure."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dataset = models.ForeignKey(DjangoDataset, on_delete=models.PROTECT, related_name="deletion_runs")
    model = models.ForeignKey(DjangoModel, null=True, on_delete=models.PROTECT, related_name="deletion_runs")
    target = models.CharField(max_length=80)
    action = models.CharField(max_length=24)
    idempotency_key = models.CharField(max_length=128)
    plan = models.JSONField(default=dict)
    completed = models.JSONField(default=list)
    task_id = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=16, default="QUEUED")
    step = models.CharField(max_length=200, default="Waiting for cleanup")
    error = models.JSONField(default=dict)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True)
    lease_owner = models.UUIDField(null=True)
    lease_until = models.DateTimeField(null=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        constraints: ClassVar[list] = [
            models.UniqueConstraint(fields=["target", "idempotency_key"], name="unique_deletion_request"),
            models.UniqueConstraint(fields=["target"], condition=~models.Q(status="SUCCEEDED"), name="one_pending_deletion"),
            models.CheckConstraint(condition=models.Q(status__in=["QUEUED", "RUNNING", "RETRY_WAIT", "NEEDS_REVIEW", "SUCCEEDED"]), name="valid_deletion_status"),
            models.CheckConstraint(condition=models.Q(action__in=["model_files", "model", "dataset", "annotations"]), name="valid_deletion_action"),
        ]
