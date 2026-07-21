import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from insightclass.web import server


class WebPathSecurityTests(unittest.TestCase):
    def test_class_names_use_bundled_read_only_resource(self):
        self.assertEqual(
            server.CLASS_CONFIG,
            server._RESOURCE_DIR / "configs" / "classes.yaml",
        )
        self.assertEqual(
            server._load_class_display_names(),
            {
                "phone_use": "玩手机",
                "talking": "交谈",
                "sleeping": "打瞌睡",
                "standing": "站立",
            },
        )

    def test_experiment_artifact_cannot_escape_experiments_root(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "experiments"
            root.mkdir()
            with patch.object(server, "EXPERIMENTS_ROOT", root):
                with self.assertRaises(HTTPException) as raised:
                    asyncio.run(server.get_results_csv("../outside"))

        self.assertEqual(raised.exception.status_code, 400)

    def test_spa_file_cannot_escape_frontend_root(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "frontend"
            root.mkdir()
            (root / "index.html").write_text("index", encoding="utf-8")
            (Path(tmp_dir) / "secret.txt").write_text("secret", encoding="utf-8")
            with patch.object(server, "_FRONTEND_DIST", root):
                with self.assertRaises(HTTPException) as raised:
                    asyncio.run(server.serve_spa("../secret.txt"))

        self.assertEqual(raised.exception.status_code, 404)

    def test_spa_unknown_route_falls_back_to_index(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            index_path = root / "index.html"
            index_path.write_text("index", encoding="utf-8")
            with patch.object(server, "_FRONTEND_DIST", root):
                response = asyncio.run(server.serve_spa("dashboard"))

        self.assertEqual(Path(response.path), index_path)


if __name__ == "__main__":
    unittest.main()
