#

To create prodigy tables run this once:

```sh
export $(cat .env)
cat prodigy.json.in | envsubst > prodigy.json

python test_database.py
```

Then apply

```sh
psql -f prodigy.sql
```

Template sql

```sh
template_jinja2 examples.sql.jinja2 \
'{"fasttext_labels": "arb_Arab,eng_Latn,rus_Cyrl,spa_Latn", "limit": "limit 10" , "dataset_name": "ads" }' > examples.sql
```

Get 10 examples from database which have not been labeled

```sh
template_jinja2 examples.sql.jinja2 \
'{"fasttext_labels": "arb_Arab,eng_Latn,rus_Cyrl,spa_Latn", "limit": "limit 10" , "dataset_name": "ads" }' | \
psql --quiet -t -A -F"\n"
```
