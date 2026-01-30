# development

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

then ensure k8s cluster with postgres expose , see <https://k3d.io/v5.3.0/usage/exposing_services/#2-via-nodeport>

```sh
# use '--agent 2' for multi node cluster 
k3d cluster create lts --registry-create lts-registry:5500 \
--api-port 6550 -p "8081:80@loadbalancer" -p "30001:30001@loadbalancer" #-p "30001:30001@server:0" # --agents 2

#or edit
#k3d cluster edit lts --port-add 30001:30001@loadbalancer

# FIXME #can import from host docker like this
# docker pull --platform linux/amd64 postgres:18
# k3d image import postgres:18 --cluster=lts

k apply -f postgres.yaml 

#k port-forward svc/postgres-svc 30001:30001
```

verify postgres up and create django schema if needed

```sh
export $(cat .env | sed '/^#/d')

psql -c "create schema django_schema;"
```

migrate/create superuser once if needed

```sh
python -m django createsuperuser --no-input --settings site_example.settings
# to delete superuser 
psql -c "delete from django_schema.auth_user where username='superuser';"
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
