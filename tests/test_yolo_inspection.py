import tempfile
import unittest
from pathlib import Path

from insightclass.data.yolo import inspect_yolo_dataset


class YoloInspectionTests(unittest.TestCase):
    def test_inspect_yolo_dataset_reports_distribution(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            for split in ("train", "val", "test"):
                (root / "images" / split).mkdir(parents=True)
                (root / "labels" / split).mkdir(parents=True)
            image_path = root / "images" / "train" / "demo.jpg"
            image_path.write_bytes(b"fake")
            label_path = root / "labels" / "train" / "demo.txt"
            label_path.write_text("0 0.5 0.5 0.3 0.3\n", encoding="utf-8")

            report = inspect_yolo_dataset(root, ["phone_use"])

            self.assertEqual(report["split_counts"]["train"], 1)
            self.assertEqual(report["class_distribution"]["phone_use"], 1)


if __name__ == "__main__":
    unittest.main()
