#

`all_data.jsonl` is what would be a large dataset in real project (its copy of news_headlines.jsonl from prodigy NER )

eg convert that to csv and load to postgres

```sh
python -m kedro run --pipeline=convert
kedro run --pipeline=ingest
```

then

`examples.jsonl` is some of the examples from the dataset for labelling

run pipeline load examples

```sh
kedro run --pipeline=load_examples
```

and verify like this

```sh
prodigy myrecipes.textcat.custom-model news_headlines ./data/00_examples/examples.jsonl -l POS,NEG
```

or

```sh
python -m prodigy myrecipes.textcat.custom-model news_headlines ./data/00_examples/examples.jsonl -l POS,NEG
```

## build image for label-train-serve

```sh
docker build --platform=linux/arm64 \
--build-arg UV_INDEX_PRODIGY_USERNAME=$UV_INDEX_PRODIGY_USERNAME \
--build-arg UV_INDEX_YSZ_USERNAME=$UV_INDEX_YSZ_USERNAME \
--build-arg UV_INDEX_YSZ_PASSWORD=$UV_INDEX_YSZ_PASSWORD \
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
