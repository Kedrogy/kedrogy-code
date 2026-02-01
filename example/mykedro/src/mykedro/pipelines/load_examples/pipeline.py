"""
This is a boilerplate pipeline 'load_examples'
generated using Kedro 1.2.0
"""

from kedro.pipeline import Node, Pipeline  # noqa

from .nodes import load_examples


def create_pipeline(**kwargs) -> Pipeline:
    return Pipeline(
        [
            Node(
                func=load_examples,
                inputs="params:load_examples_options",
                outputs="examples_jsonl",
                name="load_examples_node",
            ),
        ]
    )
