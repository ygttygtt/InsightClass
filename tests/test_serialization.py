import tempfile
import unittest
from pathlib import Path

from insightclass.utils.serialization import load_yaml, save_yaml


class SerializationTests(unittest.TestCase):
    def test_save_yaml_replaces_file_without_leaving_temp_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "app.yaml"
            path.write_text("old: true\n", encoding="utf-8")

            save_yaml(path, {"new": "value"})

            self.assertEqual(load_yaml(path), {"new": "value"})
            self.assertEqual(list(Path(tmp_dir).glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
