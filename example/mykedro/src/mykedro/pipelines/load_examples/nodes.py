"""Load unlabelled examples from a server-approved PostgreSQL source."""
from mykedro.db_queries import read_examples


def load_examples(parameters: dict) -> list[dict]:
    """Load examples using safe queries and the trusted source policy."""
    return read_examples(
        dataset_name=parameters["dataset_name"],
        table_name=parameters["data_table_name"],
        id_field=parameters["id_field"],
    )
