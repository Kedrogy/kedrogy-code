"""Build Kubernetes documents as data; serialize only at the process boundary."""

import json

from django.conf import settings

from .launch_config import LaunchConfig


def db_env(secret_name: str) -> list[dict]:
    """Reference selected DB keys without handling their values."""
    return [{"name": key, "valueFrom": {"secretKeyRef": {"name": secret_name, "key": key}}}
            for key in ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD")]


def metadata(name: str) -> dict:
    """Name resources in the configured namespace."""
    return {"name": name, "namespace": settings.KEDROGY_NAMESPACE}


def pod_spec() -> dict:
    """Workload containers have no Kubernetes API credentials or elevated rights."""
    return {"automountServiceAccountToken": False,
            "serviceAccountName": "kedrogy-workload",
            "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}}}


def container(name: str, cfg: LaunchConfig, args: list[str]) -> dict:
    """Create a container using only resolved image, path, and argv values."""
    return {"name": name, "image": cfg.image, "imagePullPolicy": "IfNotPresent",
            "workingDir": cfg.working_dir, "command": ["/app/.venv/bin/python"], "args": args,
            "securityContext": {"privileged": False, "allowPrivilegeEscalation": False,
                                "capabilities": {"drop": ["ALL"]}}}


def config_map(name: str, filename: str, parameters: dict) -> dict:
    """JSON is also valid YAML; preserve scalars in nested Kedro configuration."""
    return {"apiVersion": "v1", "kind": "ConfigMap", "metadata": metadata(name),
            "data": {filename: json.dumps(parameters, ensure_ascii=False)}}


def pvc(model_id: int) -> dict:
    """Create the model artifact volume without user-controlled resource names."""
    return {"apiVersion": "v1", "kind": "PersistentVolumeClaim",
            "metadata": metadata(f"pvc-model-{model_id}") | {"labels": {"kedrogy/model-id": str(model_id), "app.kubernetes.io/managed-by": "kedrogy"}},
            "spec": {"accessModes": ["ReadWriteOnce"], "storageClassName": "local-path",
                     "resources": {"requests": {"storage": "1Gi"}}}}


def training(cfg: LaunchConfig, model_id: int, labels: tuple[str, ...], *,
             run_id: str, options: dict | None = None) -> list[dict]:
    """Build a training ConfigMap and Job with read-only database access."""
    name = f"parameters-{run_id}"
    conf = config_map(name, "parameters_train.yml", {"model_options": {
        "dataset_name": cfg.dataset_name, "labels": list(labels), "data_seed": 123, "seed": 123,
        **(options or {}), "run_id": run_id, "image": cfg.image}})
    conf["immutable"] = True
    conf["metadata"]["labels"] = {"kedrogy/run-id": run_id, "kedrogy/model-id": str(model_id)}
    train = container("train", cfg, ["-m", "kedro", "run", "--pipeline=train"])
    train["env"] = db_env("kedrogy-db-reader") + [
        {"name": "KEDROGY_POD_UID", "valueFrom": {"fieldRef": {"fieldPath": "metadata.uid"}}},
        {"name": "HF_HUB_OFFLINE", "value": "1"}, {"name": "TOKENIZERS_PARALLELISM", "value": "false"}]
    train["terminationMessagePolicy"] = "File"
    train["volumeMounts"] = [
        {"name": "models", "mountPath": f"{cfg.working_dir}/data/06_models"},
        {"name": "parameters", "mountPath": f"{cfg.working_dir}/conf/base/parameters_train.yml", "subPath": "parameters_train.yml", "readOnly": True}]
    spec = pod_spec() | {"restartPolicy": "Never", "containers": [train], "volumes": [
        {"name": "models", "persistentVolumeClaim": {"claimName": f"pvc-model-{model_id}"}},
        {"name": "parameters", "configMap": {"name": name}}]}
    labels = {"kedrogy/run-id": run_id}
    return [conf, {"apiVersion": "batch/v1", "kind": "Job",
                   "metadata": metadata(f"train-{run_id}") | {"labels": labels},
                   "spec": {"backoffLimit": 1,
                            "activeDeadlineSeconds": getattr(settings, "KEDROGY_TRAIN_TIMEOUT", 3600),
                            "template": {"metadata": {"labels": labels}, "spec": spec}}}]


def serving(cfg: LaunchConfig, model_id: int, preprocessor: str, *,
            artifact_path: str, serving_run_id: str, training_run_id: str, artifact: dict) -> list[dict]:
    """Build inference resources without database credentials."""
    name = f"serve-{serving_run_id}"
    labels = {"app.kubernetes.io/name": name}
    revision = {"kedrogy/serving-id": serving_run_id}
    args = ["-m", "ysz.predict", f"data/06_models/{artifact_path}",
            "--serving-run-id", serving_run_id, "--training-run-id", training_run_id,
            "--artifact", json.dumps(artifact)]
    if preprocessor:
        args += ["-p", preprocessor]
    predict = container("predict", cfg, args)
    predict["ports"] = [{"containerPort": 8888}]
    predict["env"] = [{"name": "HF_HUB_OFFLINE", "value": "1"}, {"name": "TOKENIZERS_PARALLELISM", "value": "false"}]
    predict["startupProbe"] = {"httpGet": {"path": "/readyz", "port": 8888}, "periodSeconds": 5, "timeoutSeconds": 2,
                                "failureThreshold": max(1, settings.KEDROGY_SERVE_TIMEOUT // 5)}
    predict["readinessProbe"] = {"httpGet": {"path": "/readyz", "port": 8888}, "periodSeconds": 5, "timeoutSeconds": 2, "failureThreshold": 1}
    predict["livenessProbe"] = {"httpGet": {"path": "/livez", "port": 8888}, "periodSeconds": 10, "timeoutSeconds": 3, "failureThreshold": 6}
    predict["volumeMounts"] = [{"name": "models", "mountPath": f"{cfg.working_dir}/data/06_models", "readOnly": True}]
    spec = pod_spec() | {"containers": [predict], "volumes": [
        {"name": "models", "persistentVolumeClaim": {"claimName": f"pvc-model-{model_id}"}}]}
    return [
        {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": metadata(name) | {"labels": revision}, "spec": {
            "replicas": 1, "strategy": {"type": "Recreate"}, "selector": {"matchLabels": labels}, "template": {"metadata": {"labels": labels | revision}, "spec": spec}}},
        {"apiVersion": "v1", "kind": "Service", "metadata": metadata(f"serve-svc-{serving_run_id}") | {"labels": revision}, "spec": {
            "selector": labels | revision, "ports": [{"name": "predict", "port": 8888, "targetPort": 8888}]}}]


def verification(cfg: LaunchConfig, model_id: int, *, name: str, run_id: str,
                 attempt_id: str, path: str, labels: list[str], legacy: bool = False, artifact_version: int = 1) -> dict:
    """Verify a checkpoint from a read-only volume without database credentials."""
    args = ["-m", "mykedro.artifacts", "--path", f"data/06_models/{path}",
            "--run-id", run_id, "--attempt-id", attempt_id, "--labels", json.dumps(labels),
            "--image", cfg.image, "--artifact-version", str(artifact_version)]
    if legacy:
        args.append("--legacy")
    probe = container("verify", cfg, args)
    probe["volumeMounts"] = [{"name": "models", "mountPath": f"{cfg.working_dir}/data/06_models", "readOnly": True}]
    probe["terminationMessagePolicy"] = "File"
    spec = pod_spec() | {"restartPolicy": "Never", "containers": [probe], "volumes": [
        {"name": "models", "persistentVolumeClaim": {"claimName": f"pvc-model-{model_id}"}}]}
    return {"apiVersion": "batch/v1", "kind": "Job", "metadata": metadata(name) | {"labels": {"kedrogy/run-id": run_id, "kedrogy/model-id": str(model_id)}},
            "spec": {"backoffLimit": 0, "activeDeadlineSeconds": 300, "template": {"spec": spec}}}


def annotation(cfg: LaunchConfig, dataset_id: int) -> list[dict]:
    """Build annotation resources with separate reader and annotation credentials."""
    name = f"parameters-examples-{dataset_id}"
    conf = config_map(name, "parameters_load_examples.yml", {"load_examples_options": {
        "dataset_name": cfg.dataset_name, "data_table_name": cfg.table_name, "id_field": cfg.id_field}})
    load = container("load-examples", cfg, ["-m", "kedro", "run", f"--pipeline={cfg.pipeline}"])
    load["env"] = db_env("kedrogy-db-reader") + [
        {"name": "KEDROGY_SOURCES", "value": json.dumps(settings.KEDROGY_SOURCES)}]
    examples_mount = {"name": "examples", "mountPath": f"{cfg.working_dir}/data/00_examples"}
    load["volumeMounts"] = [examples_mount, {"name": "parameters", "mountPath": f"{cfg.working_dir}/conf/base/parameters_load_examples.yml", "subPath": "parameters_load_examples.yml", "readOnly": True}]
    create_config = container("create-prodigy-config", cfg, ["-m", "mykedro.prodigy_config", "/prodigy-json/prodigy.json"])
    create_config["env"] = db_env("kedrogy-db-annotator")
    create_config["volumeMounts"] = [{"name": "prodigy-json", "mountPath": "/prodigy-json"}]
    prodigy = container("prodigy", cfg, ["-m", "prodigy", *cfg.recipe_args])
    prodigy["env"] = [{"name": "PRODIGY_CONFIG", "value": "/prodigy-json/prodigy.json"},
                      {"name": "PRODIGY_HOST", "value": "0.0.0.0"}, {"name": "PRODIGY_PORT", "value": "8080"}]
    prodigy["ports"] = [{"containerPort": 8080}]
    prodigy["volumeMounts"] = [examples_mount, {"name": "prodigy-json", "mountPath": "/prodigy-json", "readOnly": True}]
    spec = pod_spec() | {"initContainers": [create_config, load], "containers": [prodigy], "volumes": [
        {"name": "prodigy-json", "emptyDir": {"medium": "Memory", "sizeLimit": "1Mi"}},
        {"name": "examples", "emptyDir": {"sizeLimit": "500Mi"}},
        {"name": "parameters", "configMap": {"name": name}}]}
    labels = {"app.kubernetes.io/name": "prodigy"}
    return [conf, {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": metadata("prodigy"),
                   "spec": {"replicas": 1, "selector": {"matchLabels": labels}, "template": {"metadata": {"labels": labels}, "spec": spec}}}]


def annotation_revision(cfg: LaunchConfig, dataset_id: int, run_id: str) -> list[dict]:
    """Run-specific resources prevent an older session overwriting a newer one."""
    conf, deployment = annotation(cfg, dataset_id)
    name = f"annotation-{run_id}"
    labels = {"app.kubernetes.io/name": "prodigy", "kedrogy/annotation-id": run_id,
              "kedrogy/dataset-id": str(dataset_id)}
    conf["metadata"] = metadata(name) | {"labels": labels}
    conf["immutable"] = True
    deployment["metadata"] = metadata(name) | {"labels": labels}
    deployment["spec"]["selector"] = {"matchLabels": labels}
    deployment["spec"]["strategy"] = {"type": "Recreate"}
    template = deployment["spec"]["template"]
    template["metadata"]["labels"] = labels
    spec = template["spec"]
    spec["volumes"][-1]["configMap"]["name"] = name
    health = container("annotation-health", cfg, ["-m", "myrecipes.annotation_health"])
    health["env"] = [{"name": "KEDROGY_ANNOTATION_RUN_ID", "value": run_id},
                     {"name": "KEDROGY_ANNOTATION_DATASET", "value": cfg.dataset_name}]
    health["ports"] = [{"containerPort": 8081}]
    health["readinessProbe"] = {"httpGet": {"path": "/readyz", "port": 8081}, "periodSeconds": 5, "timeoutSeconds": 3}
    health["livenessProbe"] = {"httpGet": {"path": "/livez", "port": 8081}, "periodSeconds": 10, "timeoutSeconds": 3}
    spec["containers"].append(health)
    return [conf, deployment, {"apiVersion": "v1", "kind": "Service", "metadata": metadata(name) | {"labels": labels},
            "spec": {"selector": labels, "ports": [{"name": "web", "port": 8080}, {"name": "health", "port": 8081}]}}]
