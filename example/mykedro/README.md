#

## raw data convert

`all_data.jsonl` is what would be a large dataset in real project (its copy of news_headlines.jsonl from prodigy NER )

eg convert that to csv

```sh
python -m kedro run --pipeline=convert
```

## and load dataset to postgres

for the rest of pipelines

```sh
kedro run --pipeline=ingest
```

then

`data/00_examples/examples.jsonl` is some of the examples from the dataset for labelling

## run pipeline to load examples from postgres

```sh
kedro run --pipeline=load_examples
```

## run prodigy to label loaded examples

verify locally like this

```sh
prodigy myrecipes.textcat.custom-model news_headlines ./data/00_examples/examples.jsonl -l POS,NEG
```

or

```sh
python -m prodigy myrecipes.textcat.custom-model news_headlines ./data/00_examples/examples.jsonl -l POS,NEG
```

## train a model on prodigy output from the postgres

```sh
kedro run --pipeline=train
```

## serve best model using preprocess module

```sh
python -m ysz.predict data/06_models/best/ -p a_preprocess_fun
```

and use ysz.predict server like this

```sh
> curl -H "Content-Type: application/json" http://0.0.0.0:8888/predict -d '{"text":"Hello, world"}'
{"predicted_class_id":"POS"}
```
