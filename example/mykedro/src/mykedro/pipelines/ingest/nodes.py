"""
This is a boilerplate pipeline 'ingest'
generated using Kedro 1.2.0
"""

import pandas as pd

from kedro_datasets.pandas import SQLTableDataset


def ingest(all_data: pd.DataFrame) -> SQLTableDataset:
    return all_data
