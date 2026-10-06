default_registry("kedrogy-registry.localhost:5500", host_from_cluster="kedrogy-registry:5000")
watch_settings(ignore=["example", ".venv", ".local", ".env", "reports"])
docker_build(
    "kedrogy-backend:dev",
    ".",
    dockerfile="Dockerfile",
    secret=[
        "id=prodigy_username,env=UV_INDEX_PRODIGY_USERNAME",
        "id=ysz_username,env=UV_INDEX_YSZ_USERNAME",
        "id=ysz_password,env=UV_INDEX_YSZ_PASSWORD",
    ],
    live_update=[
        sync("mysite/src", "/app/mysite/src"),
        sync("kedrogy/src", "/app/kedrogy/src"),
    ],
)
local("python3 scripts/render_infrastructure.py --profile local --backend-image kedrogy-backend:dev --output-dir .local/tilt")
k8s_yaml(".local/tilt/mysite.yaml")
k8s_resource("mysite", port_forwards=["8002:8000"])
