"""
This is a boilerplate pipeline 'train'
generated using Kedro 1.2.0
"""

from kedro.pipeline import Node, Pipeline  # noqa

from .nodes import labelled_examples, jsonl_to_fasttext, split_examples, train


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
                inputs=["labelled_examples", "params:model_options"],
                outputs="dataset_fasttext",
                name="jsonl_to_fasttext_node",
            ),
            Node(
                func=split_examples,
                inputs=["dataset_fasttext", "params:model_options"],
                outputs="model_input",
                name="train_test_split_node",
            ),
            Node(
                func=train,
                inputs=["model_input", "params:model_options"],
                outputs=None,  # "model",
                name="train_node",
            ),
        ]
    )
