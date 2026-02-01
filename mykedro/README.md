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
