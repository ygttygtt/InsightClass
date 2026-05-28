from __future__ import annotations

import random
from pathlib import Path

from insightclass.exceptions import ConfigError
from insightclass.schemas import DatasetManifest
from insightclass.utils.paths import is_video_file
from insightclass.utils.serialization import load_yaml, save_yaml


def discover_videos(raw_videos_dir: str | Path) -> list[Path]:
    directory = Path(raw_videos_dir).resolve()
    if not directory.exists():
        raise FileNotFoundError(f"Raw video directory not found: {directory}")
    return sorted(path for path in directory.rglob("*") if path.is_file() and is_video_file(path))


def build_split_map(
    videos: list[Path],
    train_ratio: float = 0.7,
    val_ratio: float = 0.2,
    seed: int = 42,
) -> dict[str, list[str]]:
    if not videos:
        raise ConfigError("No videos found for split generation.")
    if train_ratio <= 0 or val_ratio < 0 or train_ratio + val_ratio >= 1:
        raise ConfigError("Invalid split ratios. Expected train_ratio + val_ratio < 1.")

    shuffled = list(videos)
    random.Random(seed).shuffle(shuffled)
    total = len(shuffled)
    train_end = max(1, int(total * train_ratio))
    val_end = min(total, train_end + max(1 if total >= 3 else 0, int(total * val_ratio)))
    if val_end == train_end and total >= 2:
        val_end = min(total, train_end + 1)
    return {
        "train": [path.name for path in shuffled[:train_end]],
        "val": [path.name for path in shuffled[train_end:val_end]],
        "test": [path.name for path in shuffled[val_end:]],
    }


def create_manifest(
    dataset_name: str,
    dataset_version: str,
    raw_videos_dir: str,
    processed_dir: str,
    classes: list[str],
    display_names: dict[str, str],
    seed: int = 42,
    train_ratio: float = 0.7,
    val_ratio: float = 0.2,
    notes: str = "",
) -> DatasetManifest:
    videos = discover_videos(raw_videos_dir)
    splits = build_split_map(videos, train_ratio=train_ratio, val_ratio=val_ratio, seed=seed)
    video_metadata = {
        video.name: {
            "source_path": str(video.resolve()),
            "relative_parent": str(video.parent.relative_to(Path(raw_videos_dir).resolve()))
            if Path(raw_videos_dir).resolve() in video.resolve().parents
            else "",
        }
        for video in videos
    }
    return DatasetManifest(
        dataset_name=dataset_name,
        dataset_version=dataset_version,
        raw_videos_dir=str(Path(raw_videos_dir).resolve()),
        processed_dir=str(Path(processed_dir).resolve()),
        classes=classes,
        display_names=display_names,
        splits=splits,
        video_metadata=video_metadata,
        notes=notes,
    )


def save_manifest(path: str | Path, manifest: DatasetManifest) -> None:
    save_yaml(path, manifest.to_dict())


def load_manifest(path: str | Path) -> DatasetManifest:
    data = load_yaml(path)
    return DatasetManifest(**data)
