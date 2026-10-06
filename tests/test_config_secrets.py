"""Secret serialization checks using synthetic values only."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mykedro.prodigy_config import write_config


class ConfigTests(unittest.TestCase):
    def test_secret_round_trip_and_permissions(self):
        value = 'synthetic-"quote"-\\backslash-$dollar-\'apostrophe'
        env = {'PGHOST': 'localhost', 'PGPORT': '5432', 'PGDATABASE': 'test', 'PGUSER': 'test', 'PGPASSWORD': value}
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, env):
            path = Path(directory) / 'prodigy.json'
            path.touch(mode=0o644)
            write_config(path)
            config = json.loads(path.read_text())
            self.assertEqual(config['db_settings']['kedrogy_postgresql']['password'], value)
            self.assertEqual(config['db_settings']['kedrogy_postgresql']['port'], '5432')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_missing_secret_has_safe_diagnostic(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(ValueError, 'PGPASSWORD'):
            write_config(Path('/unused'))


if __name__ == '__main__':
    unittest.main()
