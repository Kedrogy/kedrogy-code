# syntax=docker/dockerfile:1
# Dockerfile for Tilt 

FROM python:3.12-slim

RUN apt-get update && apt install -y postgresql-common \
    && YES=yes /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh \
    && apt-get install -y --no-install-recommends \
    libpq-dev \
    postgresql-client-18 \
    g++ \
    ripgrep \
    git \
    openssh-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/#install-using-native-package-management
RUN apt-get update && apt-get install -y \
    apt-transport-https ca-certificates curl gnupg \
    && curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.35/deb/Release.key | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg \
    && chmod 644 /etc/apt/keyrings/kubernetes-apt-keyring.gpg \
    && echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.35/deb/ /' | tee /etc/apt/sources.list.d/kubernetes.list \
    && chmod 644 /etc/apt/sources.list.d/kubernetes.list \
    && apt-get update \
    && apt-get install -y \
    kubectl \
    && rm -rf /var/lib/apt/lists/*
    
COPY --from=ghcr.io/astral-sh/uv:0.9.28 /uv /uvx /bin/

# https://docs.docker.com/build/ci/github-actions/secrets/
RUN mkdir -p -m 0700 ~/.ssh && ssh-keyscan github.com >> ~/.ssh/known_hosts

WORKDIR /app

COPY contracts /app/contracts
COPY pyproject.toml uv.lock /app/
COPY mysite/pyproject.toml mysite/README.md /app/mysite/
COPY mysite/src /app/mysite/src
COPY kedrogy/pyproject.toml kedrogy/README.md /app/kedrogy/
COPY kedrogy/src /app/kedrogy/src

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=ssh \
    --mount=type=secret,id=prodigy_username,env=UV_INDEX_PRODIGY_USERNAME \
    --mount=type=secret,id=ysz_username,env=UV_INDEX_YSZ_USERNAME \
    --mount=type=secret,id=ysz_password,env=UV_INDEX_YSZ_PASSWORD \
    uv sync --all-packages --no-dev --locked

RUN /app/.venv/bin/python -m django collectstatic --noinput --settings mysite.test_settings

ENTRYPOINT ["/app/.venv/bin/python"]
