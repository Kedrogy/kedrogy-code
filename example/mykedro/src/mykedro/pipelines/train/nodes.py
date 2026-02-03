"""
This is a boilerplate pipeline 'train'
generated using Kedro 1.2.0
"""

from collections.abc import Iterable

from srsly.util import JSONInput
import psycopg


def labelled_examples(parameters: dict) -> Iterable[JSONInput]:
    dataset_name = parameters["dataset_name"]
    with psycopg.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
    select replace(encode(content, 'escape'), '\\"', '\"')::json
    FROM
        link
    LEFT JOIN dataset ON dataset.id = link.dataset_id
    LEFT JOIN example ON example.id = link.example_id
    WHERE
    dataset.name = '{dataset_name}';
                """)
            labelled_jsonl = [x[0] for x in cur.fetchall()]
    return labelled_jsonl


def jsonl_to_fasttext(stream: Iterable[JSONInput]) -> Iterable[JSONInput]:
    def eg_to_fasttext(eg):
        if eg["answer"] == "accept":
            # like this
            # https://flairnlp.github.io/docs/tutorial-training/how-to-load-custom-dataset#fasttext-format
            LABEL = eg["label"]  # "ADS"
            # print(f"__label__{LABEL} ", end="")
        elif eg["answer"] == "reject":
            LABEL = "__label__OTHER"  # "OTHER"
            # print(f"__label__OTHER ", end="")
        else:
            return None  # ignore
        return {"label": LABEL, "text": eg["text"]}

    all = []
    for eg in stream:
        eg_fasttext = eg_to_fasttext(eg)
        if eg_fasttext:
            all.append(eg_fasttext)
            # yield eg_to_fasttext(eg)
    return all
