#

uv workspace example with kedro pipelines and custom recipe

```sh
uv sync --all-packages --dev --no-managed-python
```

build image for label-train-serve , TODO:how to tilt this, but make tilt NOT modify tag of the pushed image on the cluster  

NB Dockerfile-example has to pull ../predict for development , hence build from the root of the repository

```sh
cd ..

docker build --platform=linux/arm64 \
--build-arg UV_INDEX_PRODIGY_USERNAME=$UV_INDEX_PRODIGY_USERNAME \
--build-arg UV_INDEX_YSZ_USERNAME=$UV_INDEX_YSZ_USERNAME \
--build-arg UV_INDEX_YSZ_PASSWORD=$UV_INDEX_YSZ_PASSWORD \
--ssh default=~/.ssh/team-ysz \
-t kedrogy-registry.localhost:5500/mykedro:latest \
-f Dockerfile-example .
```

verify , all should run

```sh
docker run --platform linux/arm64 kedrogy-registry.localhost:5500/mykedro:latest -m prodigy 

docker run --platform linux/arm64 kedrogy-registry.localhost:5500/mykedro:latest -m kedro

docker run --platform linux/arm64 kedrogy-registry.localhost:5500/mykedro:latest -m ysz.predict
```

or inspect image

```sh
docker run --platform linux/arm64 --rm -it --entrypoint /bin/bash  kedrogy-registry.localhost:5500/mykedro:latest 
```

and push to cluster

```sh
docker push kedrogy-registry.localhost:5500/mykedro:latest 
```

to use on k3d cluster manifest should be

```yaml
      containers:
        - name: prodigy
          # XXX Tilt image
          image: kedrogy-registry:5000/mykedro:latest
```
