# development

For the current source-import, annotation, serving and rollout contracts, see
[Source and model contracts](SOURCE_AND_MODEL_CONTRACTS.md).

THINKME golang/rust rewrite to bundle everything in one executable here <https://go.dev/doc/articles/wiki/#tmp_1> + rust axum /and embed assets to rust

to also get dev dependencies copy .env-example to .env and set

```
UV_INDEX_YSZ_PASSWORD=
UV_INDEX_PRODIGY_USERNAME=
```

then

```sh
export $(cat .env | sed '/^#/d')
uv sync --all-packages --dev --no-managed-python
```

NB: django>=6.0 only supports >=3.12

```sh
brew install python@3.12

# to build psycopg2 get 
# brew install libpq

# to link psycopg2 against 
# brew install openssl
export LDFLAGS="-L/opt/homebrew/opt/openssl/lib"
export CPPFLAGS="-I/opt/homebrew/opt/openssl/include"
```

## django+jupyter

first run

```sh
cd notebooks
python -m django shell_plus --notebook --settings mysite.settings
```

then connect notebook to that kernel Django Shell-Plus kernel and eg try

```sh
from kedrogy.models import DjangoDataset
```

## tilt

<https://docs.tilt.dev/example_python.html>

```sh
curl -fsSL https://raw.githubusercontent.com/tilt-dev/tilt/master/scripts/install.sh | bash
```

```sh
tilt up 
```

## build docker image

```sh
DOCKER_BUILDKIT=1 docker build --platform=linux/arm64 \
--ssh default \
--secret id=prodigy_username,env=UV_INDEX_PRODIGY_USERNAME \
-t kedrogy-registry.localhost:5500/mysite:latest \
-f Dockerfile-tilt .

docker build --platform=linux/arm64 \
--secret id=prodigy_username,env=UV_INDEX_PRODIGY_USERNAME \
-t kedrogy-registry.localhost:5500/mysite:latest \
-f Dockerfile-tilt .
```

verify

```sh
docker run --platform linux/arm64 --rm -it kedrogy-registry.localhost:5500/mysite:latest -m django runserver --settings mysite.settings
```

## cluster setup

then ensure k8s cluster with postgres expose , see <https://k3d.io/v5.3.0/usage/exposing_services/#2-via-nodeport>

```sh
# use '--agent 2' for multi node cluster 
k3d cluster create kedrogy --registry-create kedrogy-registry:5500 \
--api-port 6550 -p "8081:80@loadbalancer" -p "30001:30001@loadbalancer" #-p "30001:30001@server:0" # --agents 2

#or edit
#k3d cluster edit kedrogy --port-add 30001:30001@loadbalancer
```

or stop/start

```sh
k3d cluster start kedrogy
```

import image

```sh
> docker exec -it k3d-kedrogy-server-0 uname -m
aarch64

# k3d image import postgres:18 --cluster=lts#this does not work on macbook

# pull first , if needed
docker pull --platform linux/aarch64 postgres:18

docker save --platform linux/aarch64 postgres:18 > postgres.tar
k3d image import --cluster=kedrogy ./postgres.tar

# verify: list images 
> docker exec k3d-kedrogy-server-0 crictl images
IMAGE                                        TAG                 IMAGE ID            SIZE
docker.io/library/postgres                   18                  f43f1abd80181       161MB

```

then

```sh
k apply -f postgres.yaml 

#k port-forward svc/postgres-svc 30001:30001
```

verify postgres up and create django schema IF NEEDED

```sh
export $(cat .env | sed '/^#/d')

psql -c "create schema django_schema;"
```

## maybe Get matching version of kubectl

v1.31.5 is `k3d cluster create mycluster`

```sh
# -s is silent
sudo bash -c 'curl -Ls https://dl.k8s.io/v1.31.5/kubernetes-client-darwin-arm64.tar.gz | tar xOvf - --strip-components=3 kubernetes/client/bin/kubectl > /usr/local/bin/kubectl && chmod +x /usr/local/bin/kubectl '
```

or via brew

```sh
brew tap homebrew/core --force
brew edit kubernetes-cli@1.29
#and comment out line like this 
# # disable! date: "2025-02-28", because: :deprecated_upstream

```

## troubleshooting

```sh
> PRODIGY_CONFIG=`pwd`/prodigy.json PRODIGY_LOGGING=verbose PRODIGY_BASIC_AUTH_USER=prodigy-user PRODIGY_BASIC_AUTH_PASS="$PRODIGY_BASIC_AUTH_PASS" PRODIGY_HOST=0.0.0.0 PRODIGY_PORT=8080 prodigy myrecipes.textcat.custom-model news_headlines ./data/00_examples/examples.jsonl -l POS,NEG
15:15:08: RECIPE: Calling recipe 'myrecipes.textcat.custom-model'
15:15:08: SORTER: Resort stream to prefer uncertain scores (bias 0.0)
15:15:08: /Users/me/ysz-vc/kedrogy/mykedro/prodigy.json
15:15:08: /Users/me/ysz-vc/kedrogy/mykedro/prodigy.json
15:15:08: VALIDATE: Validating components returned by recipe
15:15:08: CONTROLLER: Initialising from recipe
15:15:08: CONTROLLER: Recipe Config
15:15:08: {'dataset': 'news_headlines', 'recipe_name': 'myrecipes.textcat.custom-model', 'db': 'postgresql', 'db_settings': {'postgresql': {'user': SecretStr('**********'), 'password': SecretStr('**********'), 'dbname': SecretStr('**********'), 'host': SecretStr('**********')}}}
15:15:08: VALIDATE: Creating validator for view ID 'classification'
15:15:08: CONTROLLER: Using `no_overlap` router.
15:15:08: VALIDATE: Validating Prodigy and recipe config
⚠ Prodigy automatically assigned an input/task hash because it was
missing. This automatic hashing will be deprecated as of Prodigy v2 because it
can lead to unwanted duplicates in custom recipes if the examples deviate from
the default assumptions. More information can found on the docs:
https://prodi.gy/docs/api-components#set_hashes
15:15:08: /Users/me/ysz-vc/kedrogy/mykedro/prodigy.json
15:15:08: /Users/me/ysz-vc/kedrogy/mykedro/prodigy.json
15:15:08: DB: Creating unstructured dataset 'news_headlines'
Added dataset news_headlines to database PostgreSQL.
15:15:08: DB: Creating unstructured dataset '2026-02-01_15-15-08'
15:15:08: {'created': datetime.datetime(2026, 2, 1, 15, 15, 8)}
15:15:08: CORS: initialized with wildcard "*" CORS origins

✨  Starting the web server at http://0.0.0.0:8080 ...
Open the app in your browser and start annotating!

INFO:     Started server process [62364]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)
```

with

```sh
> cat prodigy.json 
{"db": "postgresql", "db_settings": {"postgresql": {"user": "postgres", "password": "<set from PGPASSWORD>", "dbname": "mysite", "host": "localhost"}}}

```
