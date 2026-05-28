from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from insightclass.utils.paths import ensure_dir
from insightclass.utils.serialization import save_json, save_yaml


def _read_label_file(path: Path) -> list[tuple[int, float, float, float, float]]:
    rows: list[tuple[int, float, float, float, float]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 5:
            raise ValueError(f"Expected 5 columns in YOLO label file: {path}")
        class_id, x_center, y_center, width, height = parts
        rows.append((int(class_id), float(x_center), float(y_center), float(width), float(height)))
    return rows


def inspect_yolo_dataset(
    dataset_root: str | Path,
    class_names: list[str],
    min_box_area: float = 0.0005,
) -> dict[str, Any]:
    root = Path(dataset_root)
    labels_root = root / "labels"
    images_root = root / "images"
    report: dict[str, Any] = {
        "dataset_root": str(root.resolve()),
        "class_names": class_names,
        "split_counts": {},
        "class_distribution": {},
        "issues": {
            "missing_label_files": [],
            "empty_label_files": [],
            "invalid_class_ids": [],
            "out_of_bounds_boxes": [],
            "tiny_boxes": [],
        },
        "sample_images_per_split": defaultdict(list),
    }
    distribution = Counter()

    for split in ("train", "val", "test"):
        image_dir = images_root / split
        label_dir = labels_root / split
        image_files = sorted(
            path for path in image_dir.glob("*") if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}
        )
        report["split_counts"][split] = len(image_files)
        report["sample_images_per_split"][split] = [path.name for path in image_files[:10]]
        for image_path in image_files:
            label_path = label_dir / f"{image_path.stem}.txt"
            if not label_path.exists():
                report["issues"]["missing_label_files"].append(str(label_path.resolve()))
                continue
            rows = _read_label_file(label_path)
            if not rows:
                report["issues"]["empty_label_files"].append(str(label_path.resolve()))
                continue
            for class_id, x_center, y_center, width, height in rows:
                if class_id < 0 or class_id >= len(class_names):
                    report["issues"]["invalid_class_ids"].append(
                        {"label_path": str(label_path.resolve()), "class_id": class_id}
                    )
                    continue
                distribution[class_names[class_id]] += 1
                if not (0 <= x_center <= 1 and 0 <= y_center <= 1 and 0 < width <= 1 and 0 < height <= 1):
                    report["issues"]["out_of_bounds_boxes"].append(
                        {"label_path": str(label_path.resolve()), "box": [x_center, y_center, width, height]}
                    )
                if width * height < min_box_area:
                    report["issues"]["tiny_boxes"].append(
                        {"label_path": str(label_path.resolve()), "box": [x_center, y_center, width, height]}
                    )

    report["class_distribution"] = dict(distribution)
    report["sample_images_per_split"] = dict(report["sample_images_per_split"])
    return report


def write_yolo_dataset_yaml(
    dataset_root: str | Path,
    classes: list[str],
    output_path: str | Path,
) -> Path:
    root = Path(dataset_root).resolve()
    payload: dict[str, Any] = {
        "path": str(root),
        "train": "images/train",
        "val": "images/val",
        "names": {index: name for index, name in enumerate(classes)},
    }
    if (root / "images" / "test").is_dir() and any((root / "images" / "test").iterdir()):
        payload["test"] = "images/test"
    save_yaml(output_path, payload)
    return Path(output_path)


def save_inspection_report(output_path: str | Path, report: dict[str, Any]) -> Path:
    ensure_dir(Path(output_path).parent)
    save_json(output_path, report)
    return Path(output_path)
