"""
This is a boilerplate pipeline 'load_examples'
generated using Kedro 1.2.0
"""

import json

import psycopg

from ysz.kedro_datasets.srsly_dataset import SrslyDataset


def load_examples(parameters: dict) -> SrslyDataset:
    data_table_name = parameters["data_table_name"]
    dataset_name = parameters["dataset_name"]
    id_field = parameters["id_field"]

    with psycopg.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                with x as (
                            SELECT
                                cast(replace(encode(content, 'escape'), '\\"', '\"')::json #>> '{{meta,{id_field} }}' AS INTEGER)
                                AS {id_field}
                            FROM
                                link
                            LEFT JOIN dataset ON dataset.id = link.dataset_id
                            LEFT JOIN example ON example.id = link.example_id
                            WHERE
                            dataset.name = '{dataset_name}'
                )
                select 
                -- or jsonb_pretty instead of json_serialize
                json_serialize(
                    json_build_object('text', text, -- or to_json(text::text) etc 
                    'meta', json_build_object('{id_field}', {id_field}
                                            , 'source', all_data.source
                    )) 
                )
                from {data_table_name}
                where 
                {id_field} not in (select * from x)
                and text is not null 
                limit 5
                ;
                """)

            examples = [json.loads(x[0]) for x in cur.fetchall()]

    return examples
