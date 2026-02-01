"""
This is a boilerplate pipeline 'convert'
generated using Kedro 1.2.0
"""

import pandas as pd

from ysz.kedro_datasets.srsly_dataset import SrslyDataset


def convert(all_data_jsonl: SrslyDataset) -> pd.DataFrame:
    df = pd.DataFrame.from_records(all_data_jsonl)
    # for index, r in df.iterrows():
    #     df.loc[index, "meta"]["id"] = index
    df = df.reset_index().rename(columns={"index": "id"})
    df["source"] = df["meta"].apply(lambda m: m["source"])

    return df[["id", "text", "source"]]
