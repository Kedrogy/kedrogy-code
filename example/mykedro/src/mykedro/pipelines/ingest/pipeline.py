"""
This is a boilerplate pipeline 'ingest'
generated using Kedro 1.2.0
"""

from kedro.pipeline import Node, Pipeline  # noqa

from .nodes import ingest


def create_pipeline(**kwargs) -> Pipeline:
    return Pipeline(
        [
            Node(
                func=ingest,
                inputs="all_data",
                outputs="all_data_postgres",
                name="ingest_node",
            ),
        ]
    )
