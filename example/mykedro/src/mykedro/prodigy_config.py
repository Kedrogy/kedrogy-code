"""Write Prodigy database configuration without shell interpolation or logs."""

import json
import os
import sys
from pathlib import Path


def write_config(path: Path) -> None:
    """Create a private config file; special characters remain exact JSON values."""
    keys = {"host": "PGHOST", "port": "PGPORT", "dbname": "PGDATABASE",
            "user": "PGUSER", "password": "PGPASSWORD"}
    missing = [key for key in keys.values() if not os.environ.get(key)]
    if missing:
        raise ValueError("Missing settings: " + ", ".join(missing))
    config = {"db": "kedrogy_postgresql", "db_settings": {"kedrogy_postgresql": {
        name: os.environ[key] for name, key in keys.items()}}}
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        json.dump(config, file)


if __name__ == "__main__":
    write_config(Path(sys.argv[1]))
