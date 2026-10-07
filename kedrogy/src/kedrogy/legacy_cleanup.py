"""Explicit, deletion-only ownership review for the original fixed-name layout.

Review records exact identities and a connected resource graph. It never patches
Kubernetes labels, adopts a serving revision or verifies a model checkpoint.
"""

import hashlib
import json

import yaml
from django.conf import settings
from django.core import signing
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .kubernetes import OperationError, command
from .models import DjangoDataset, DjangoModel
from .operation_control import resource_ref
from .serving_resources import namespace_uid
from .training import _get

SALT = "kedrogy.legacy-cleanup-review.v1"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def resource_digest(document):
    metadata = document["metadata"]
    return digest({"spec": document.get("spec"), "data": document.get("data"),
                   "binaryData": document.get("binaryData"), "immutable": document.get("immutable"),
                   "labels": metadata.get("labels", {}), "owners": metadata.get("ownerReferences", [])})


def model_stamp(model):
    return digest({"id": model.pk, "dataset_id": model.on_dataset_id,
                   "binding": model.on_dataset.prodigy_dataset_name, "image": model.on_dataset.image,
                   "retired": str(model.retired_at), "dataset_retired": str(model.on_dataset.retired_at),
                   "deleting": model.resources_deleting, "dataset_deleting": model.on_dataset.deletion_pending,
                   "training": model.training_runs.exists(), "serving": model.serving_runs.exists()})


def require_legacy(model, *, for_cleanup=False):
    if (model.retired_at or (not for_cleanup and (model.resources_deleting or model.on_dataset.deletion_pending))
            or model.on_dataset.retired_at or model.training_runs.exists() or model.serving_runs.exists()):
        raise OperationError("LEGACY_REVIEW_BLOCKED", "Legacy review is only available for an idle historical model without managed runs.")


def pod_spec(document):
    spec = document.get("spec", {})
    if document["kind"] == "Pod":
        return spec
    if document["kind"] == "CronJob":
        spec = spec.get("jobTemplate", {}).get("spec", {})
    return spec.get("template", {}).get("spec", {})


def uses_config(spec, name):
    for volume in spec.get("volumes", []):
        if volume.get("configMap", {}).get("name") == name or any(
                row.get("configMap", {}).get("name") == name for row in volume.get("projected", {}).get("sources", [])):
            return True
    for container in [*spec.get("containers", []), *spec.get("initContainers", [])]:
        if any(row.get("configMapRef", {}).get("name") == name for row in container.get("envFrom", [])):
            return True
        if any(row.get("valueFrom", {}).get("configMapKeyRef", {}).get("name") == name for row in container.get("env", [])):
            return True
    return False


def selected(selector, labels):
    return bool(selector) and all(labels.get(key) == value for key, value in selector.items())


def preview(model_id, *, for_cleanup=False):
    model = get_object_or_404(DjangoModel.objects.select_related("on_dataset"), pk=model_id)
    require_legacy(model, for_cleanup=for_cleanup)
    namespace = settings.KEDROGY_NAMESPACE
    identity = namespace_uid(namespace)
    names = {"PersistentVolumeClaim": f"pvc-model-{model_id}", "Deployment": f"serve-{model_id}",
             "Service": f"serve-svc-{model_id}", "Job": f"train-{model_id}", "ConfigMap": f"parameters-train-{model_id}"}
    documents = {kind: _get(kind, name, namespace) for kind, name in names.items()}
    issues, evidence, refs = [], [], []
    for kind, document in documents.items():
        if document is None:
            issues.append(f"{kind}/{names[kind]} is missing. This incomplete legacy layout requires a separate resource review.")
            continue
        metadata = document["metadata"]
        if metadata.get("deletionTimestamp") or metadata.get("ownerReferences") or any(
                key.startswith("kedrogy/") or key == "app.kubernetes.io/managed-by" for key in metadata.get("labels", {})):
            issues.append(f"{kind}/{names[kind]} already has ownership metadata or is being deleted.")
        refs.append(resource_ref(document, namespace) | {"namespace_uid": identity, "spec_digest": resource_digest(document)})
    if all(documents.values()):
        deployment, service, job, parameters = (documents[kind] for kind in ("Deployment", "Service", "Job", "ConfigMap"))
        labels = deployment["spec"]["template"]["metadata"].get("labels", {})
        selector = service["spec"].get("selector", {})
        if (selector != {"app.kubernetes.io/name": names["Deployment"]}
                or not selected(selector, labels)
                or deployment["spec"].get("selector") != {"matchLabels": selector}):
            issues.append("The legacy Service and Deployment selectors do not agree.")
        else:
            evidence.append("The prediction Service selects this model's legacy server.")
        approved = settings.KEDROGY_ML_IMAGE_ALIASES | {settings.KEDROGY_ML_IMAGE}
        for kind in ("Deployment", "Job"):
            spec = pod_spec(documents[kind])
            claims = {v.get("persistentVolumeClaim", {}).get("claimName") for v in spec.get("volumes", []) if "persistentVolumeClaim" in v}
            containers = spec.get("containers", [])
            model_volumes = {v["name"] for v in spec.get("volumes", []) if v.get("persistentVolumeClaim", {}).get("claimName") == names["PersistentVolumeClaim"]}
            if (claims != {names["PersistentVolumeClaim"]} or len(containers) != 1
                    or containers[0].get("image") != model.on_dataset.image or containers[0].get("image") not in approved
                    or not any(m.get("name") in model_volumes and m.get("mountPath", "").rstrip("/") == "/app/mykedro/data/06_models"
                               for m in containers[0].get("volumeMounts", []))):
                issues.append(f"{kind} does not match the approved legacy image and model storage layout.")
                continue
            args = containers[0].get("args", [])
            if (containers[0].get("command") or kind == "Job" and args != ["-m", "kedro", "run", "--pipeline=train"]
                    or kind == "Deployment" and args[:3] != ["-m", "ysz.predict", "data/06_models/best/"]):
                issues.append(f"{kind} has an unexpected legacy command.")
            evidence.append(f"The {kind} mounts this model's volume at its model checkpoint path.")
        try:
            raw = parameters.get("data", {}).get("parameters_train.yml", "")
            config = yaml.safe_load(raw) if len(raw) <= 65536 else None
            binding = config.get("model_options", {}).get("dataset_name") if isinstance(config, dict) else None
        except (yaml.YAMLError, AttributeError):
            binding = None
        if not binding or binding != model.on_dataset.prodigy_dataset_name or not uses_config(pod_spec(job), names["ConfigMap"]):
            issues.append("The legacy training configuration does not match this model's annotation binding.")
        else:
            evidence.append("The training Job uses the configuration for the model's retained annotation dataset.")

        graph = command(["get", "deployments,jobs,replicasets,statefulsets,daemonsets,cronjobs,pods,services", "-o", "json"],
                        namespace=namespace, json_output=True).get("items", [])
        allowed = {deployment["metadata"]["uid"], job["metadata"]["uid"]}
        allowed.update(row["metadata"]["uid"] for row in graph if row["kind"] == "ReplicaSet" and any(
            owner.get("uid") == deployment["metadata"]["uid"] and owner.get("kind") == "Deployment" and owner.get("controller") is True
            for owner in row["metadata"].get("ownerReferences", [])))
        for row in graph:
            metadata, spec = row["metadata"], pod_spec(row)
            related = metadata["uid"] in allowed or (row["kind"] == "Pod" and any(
                owner.get("uid") in allowed and owner.get("controller") is True for owner in metadata.get("ownerReferences", [])))
            volume_used = any(v.get("persistentVolumeClaim", {}).get("claimName") == names["PersistentVolumeClaim"] for v in spec.get("volumes", []))
            selected_pod = row["kind"] == "Pod" and selected(selector, metadata.get("labels", {}))
            if not related and (volume_used or uses_config(spec, names["ConfigMap"]) or selected_pod):
                issues.append(f"Unrelated {row['kind']}/{metadata['name']} shares the legacy storage, configuration or route.")
            if row["kind"] == "Service" and metadata["uid"] != service["metadata"]["uid"] and selected(row.get("spec", {}).get("selector", {}), labels):
                issues.append(f"Service/{metadata['name']} also selects this legacy server. Review its dependency first.")
        if not issues:
            evidence.append("No unrelated workload shares the volume, training configuration or prediction route.")
    if namespace_uid(namespace) != identity:
        raise OperationError("PREVIEW_CHANGED", "The namespace changed during review. Refresh the preview.")
    plan = {"version": 1, "model_id": model.pk, "namespace": namespace, "namespace_uid": identity,
            "model_stamp": model_stamp(model), "resources": refs, "issues": sorted(set(issues)), "evidence": evidence}
    return plan | {"review_token": signing.dumps(plan, salt=SALT, compress=True)}


def confirm(model_id, token):
    try:
        reviewed = signing.loads(token, salt=SALT, max_age=600)
    except (signing.BadSignature, TypeError):
        raise OperationError("PREVIEW_CHANGED", "The legacy review expired or is invalid. Review the resources again.") from None
    if reviewed.get("model_id") != model_id or reviewed.get("issues"):
        raise OperationError("PREVIEW_CHANGED", "Resolve the ownership review conflicts before confirming.")
    fresh = preview(model_id)
    fresh.pop("review_token")
    if reviewed != fresh:
        raise OperationError("PREVIEW_CHANGED", "Resources or dependencies changed. Review the fresh inventory before confirming.")
    # All external reads finish before locks; later deletion independently checks identities/specs.
    with transaction.atomic():
        dataset_id = DjangoModel.objects.values_list("on_dataset_id", flat=True).get(pk=model_id)
        DjangoDataset.objects.select_for_update().get(pk=dataset_id)
        model = DjangoModel.objects.select_for_update().select_related("on_dataset").get(pk=model_id)
        require_legacy(model)
        if model_stamp(model) != reviewed["model_stamp"]:
            raise OperationError("PREVIEW_CHANGED", "The model changed. Review it again.")
        model.legacy_cleanup_review = reviewed | {"reviewed_at": timezone.now().isoformat()}
        model.save(update_fields=["legacy_cleanup_review"])
    return {"recorded": True, "model_id": model_id, "resource_count": len(reviewed["resources"]), "deleted": False}


def reviewed_resources(model):
    review = model.legacy_cleanup_review
    if not review:
        return []
    if review.get("namespace") != settings.KEDROGY_NAMESPACE or namespace_uid(review["namespace"]) != review.get("namespace_uid"):
        raise OperationError("RESOURCE_IDENTITY_CHANGED", "The reviewed legacy namespace changed. Review ownership again.")
    refs = []
    for ref in review["resources"]:
        current = _get(ref["kind"], ref["name"], ref["namespace"])
        if current is None:
            continue
        if current["metadata"]["uid"] != ref["uid"] or resource_digest(current) != ref["spec_digest"]:
            raise OperationError("RESOURCE_IDENTITY_CHANGED", "A reviewed legacy resource was replaced or modified. Review ownership again.")
        refs.append(ref)
    return refs
