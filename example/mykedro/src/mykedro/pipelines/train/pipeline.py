"""
This is a boilerplate pipeline 'train'
generated using Kedro 1.2.0
"""

from kedro.pipeline import Node, Pipeline  # noqa
from sklearn.model_selection import train_test_split

from .nodes import labelled_examples, jsonl_to_fasttext


def create_pipeline(**kwargs) -> Pipeline:
    return Pipeline(
        [
            Node(
                func=labelled_examples,
                inputs="params:model_options",
                outputs="labelled_examples",
                name="labelled_examples_node",
            ),
            Node(
                func=jsonl_to_fasttext,
                inputs="labelled_examples",
                outputs="dataset_fasttext",
                name="jsonl_to_fasttext_node",
            ),
            Node(
                func=train_test_split,
                inputs="dataset_fasttext",
                outputs="model_input",
                name="train_test_split_node",
            ),
        ]
    )
