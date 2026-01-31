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

# ARG UV_INDEX_PRODIGY_USERNAME 
# RUN --mount=type=cache,target=/root/.cache/uv \
#     --mount=type=bind,source=mysite/uv.lock,target=mysite/uv.lock \
#     --mount=type=bind,source=mysite/pyproject.toml,target=mysite/pyproject.toml \
#     cd mysite && \
#     uv sync --dev --frozen

COPY . /app

# # https://docs.docker.com/build/ci/github-actions/secrets/
# # this step configure git and checks the ssh key is loaded
# RUN --mount=type=ssh <<EOT
#   set -e
#   echo "Setting Git SSH protocol"
#   git config --global url."git@github.com:".insteadOf "https://github.com/"
#   (
#     set +e
#     ssh -T git@github.com
#     if [ ! "$?" = "1" ]; then
#       echo "No GitHub SSH key loaded exiting..."
#       exit 1
#     fi
#   )
# EOT
ARG UV_INDEX_PRODIGY_USERNAME 
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=ssh \
    cd mysite && \
    uv sync --dev --locked

ENTRYPOINT [ "/app/mysite/.venv/bin/python" ]
