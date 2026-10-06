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
                inputs=["all_data", "params:ingest_options"],
                outputs="import_receipt",
                name="ingest_node",
            ),
        ]
    )
