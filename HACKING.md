#

Copy .env.example , values in .env.example are for `flytectl demo` default postgres/etc

## setup

NB: django>=6.0 only supports >=3.12

```sh
brew install python@3.12

# to build psycopg2 get 
# brew install libpq

# to link psycopg2 against 
# brew install openssl
export LDFLAGS="-L/opt/homebrew/opt/openssl/lib"
export CPPFLAGS="-I/opt/homebrew/opt/openssl/include"

cd site-example 
uv sync --no-managed-python \
--all-packages 
```

Get k8s cluster eg like this

```sh
brew tap flyteorg/homebrew-tap
brew install flytectl

# to restart 
# flytectl demo teardown -v
flytectl demo start --version v1.16.3

```

That starts this version of k3s:

```sh
> k version
Server Version: v1.29.0+k3s1
```

## maybe Get matching version of kubectl

```sh
# -s is silent
sudo bash -c 'curl -Ls https://dl.k8s.io/v1.29.15/kubernetes-client-darwin-arm64.tar.gz | tar xOvf - --strip-components=3 kubernetes/client/bin/kubectl > /usr/local/bin/kubectl && chmod +x /usr/local/bin/kubectl '
```

or via brew

```sh
brew tap homebrew/core --force
brew edit kubernetes-cli@1.29
#and comment out line like this 
# # disable! date: "2025-02-28", because: :deprecated_upstream

```

## other implementations

<https://explosion.ai/blog/posh-prodigy-financial-chatbots>

![](./posh_service.svg)
