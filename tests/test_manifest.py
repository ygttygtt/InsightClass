import tempfile
import unittest
from pathlib import Path

from insightclass.data.manifest import build_split_map, create_manifest


class ManifestTests(unittest.TestCase):
    def test_build_split_map_keeps_video_names(self):
        videos = [Path(f"video_{index}.mp4") for index in range(10)]
        splits = build_split_map(videos, train_ratio=0.6, val_ratio=0.2, seed=1)
        all_names = set(splits["train"] + splits["val"] + splits["test"])
        self.assertEqual(all_names, {video.name for video in videos})

    def test_create_manifest_discovers_videos(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            raw_dir = Path(tmp_dir) / "raw"
            raw_dir.mkdir()
            (raw_dir / "a.mp4").write_bytes(b"")
            (raw_dir / "b.mp4").write_bytes(b"")
            manifest = create_manifest(
                dataset_name="demo",
                dataset_version="v1",
                raw_videos_dir=str(raw_dir),
                processed_dir=str(Path(tmp_dir) / "processed"),
                classes=["phone_use"],
                display_names={"phone_use": "玩手机"},
            )
            self.assertEqual(manifest.dataset_name, "demo")
            self.assertIn("train", manifest.splits)


if __name__ == "__main__":
    unittest.main()
