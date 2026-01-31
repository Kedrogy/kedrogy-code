from django.apps import AppConfig


class DatasetNewConfig(AppConfig):
    name = "label_train_serve"

    def ready(self):
        print("label_train_serve is ready! Executing startup code.")

        import psycopg

        # Connect to an existing database
        with psycopg.connect() as conn:
            # Open a cursor to perform database operations
            with conn.cursor() as cur:
                # Execute a command: this creates a new table
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM pg_tables
                        WHERE schemaname = 'public' AND tablename = 'dataset'
                    );        
                    """)

                dataset_table_found = cur.fetchall()[0][0]

        if not dataset_table_found:
            # https://prodi.gy/docs/api-database#setup-permissions
            from prodigy.components.db import connect

            examples = [{"text": "hello world", "_task_hash": 123, "_input_hash": 456}]

            # uses settings from prodigy.json
            db = connect()

            db.add_dataset("test_dataset")
            # check that dataset was added
            assert "test_dataset" in db

            # add examples to dataset
            db.add_examples(examples, ["test_dataset"])
            # retrieve a dataset's examples
            examples = db.get_dataset_examples("test_dataset")

            # check that examples were added
            assert len(examples) == 1
