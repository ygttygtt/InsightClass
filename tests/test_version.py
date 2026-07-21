import json
import tomllib
import unittest
from pathlib import Path

from insightclass import __version__


ROOT = Path(__file__).parents[1]


class VersionTests(unittest.TestCase):
    def test_release_version_is_consistent_across_runtimes(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        frontend = json.loads(
            (ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
        )
        frontend_lock = json.loads(
            (ROOT / "frontend" / "package-lock.json").read_text(encoding="utf-8")
        )

        self.assertEqual(project["project"]["version"], __version__)
        self.assertEqual(frontend["version"], __version__)
        self.assertEqual(frontend_lock["version"], __version__)
        self.assertEqual(frontend_lock["packages"][""]["version"], __version__)

    def test_windows_metadata_matches_release_version(self):
        metadata = (ROOT / "assets" / "windows-version-info.txt").read_text(
            encoding="utf-8"
        )
        version_tuple = tuple(int(part) for part in __version__.split(".")) + (0,)
        self.assertIn(f"filevers={version_tuple}", metadata)
        self.assertIn(f"prodvers={version_tuple}", metadata)
        self.assertIn(f"StringStruct('ProductVersion', '{__version__}')", metadata)


if __name__ == "__main__":
    unittest.main()
