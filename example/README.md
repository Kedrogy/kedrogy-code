#

uv workspace example with kedro pipelines and custom recipe

```sh
uv sync --all-packages --dev
```

build image for label-train-serve , TODO:how to tilt this, but make tilt NOT modify tag of the pushed image on the cluster  

```sh
docker build --platform=linux/arm64 \
--build-arg UV_INDEX_PRODIGY_USERNAME=$UV_INDEX_PRODIGY_USERNAME \
--build-arg UV_INDEX_YSZ_USERNAME=$UV_INDEX_YSZ_USERNAME \
--build-arg UV_INDEX_YSZ_PASSWORD=$UV_INDEX_YSZ_PASSWORD \
--ssh default=~/.ssh/team-ysz \
-t lts-registry.localhost:5500/mykedro:latest \
-f Dockerfile .
```

push

```sh
docker push lts-registry.localhost:5500/mykedro:latest 
```

to use on k3d cluster manifest should be

```yaml
      containers:
        - name: prodigy
          # XXX Tilt image
          image: lts-registry:5000/mykedro:latest
```
