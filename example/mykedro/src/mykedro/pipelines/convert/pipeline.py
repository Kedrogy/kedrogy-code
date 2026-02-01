"""
This is a boilerplate pipeline 'convert'
generated using Kedro 1.2.0
"""

from kedro.pipeline import Node, Pipeline  # noqa

from .nodes import convert


def create_pipeline(**kwargs) -> Pipeline:
    return Pipeline(
        [
            Node(
                func=convert,
                inputs="all_data_jsonl",
                outputs="all_data",
                name="convert_node",
            ),
        ]
    )
