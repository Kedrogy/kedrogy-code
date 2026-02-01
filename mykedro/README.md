#

`all_data.jsonl` is what would be a large dataset in real project (its copy of news_headlines.jsonl from prodigy NER )

`examples.jsonl` is some of the examples from the dataset for labelling

run pipeline and verify like this

```sh
prodigy myrecipes.textcat.custom-model news_headlines ./data/00_examples/examples.jsonl -l POS,NEG
```
