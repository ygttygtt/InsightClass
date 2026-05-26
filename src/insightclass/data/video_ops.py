from __future__ import annotations

import csv
from pathlib import Path

from insightclass.schemas import DatasetManifest
from insightclass.optional import require_package
from insightclass.utils.paths import ensure_dir


def extract_frames_from_manifest(
    manifest: DatasetManifest,
    fps: float,
    image_ext: str = ".jpg",
    max_frames_per_video: int | None = None,
) -> Path:
    require_package("cv2", "Frame extraction")
    import cv2

    raw_dir = Path(manifest.raw_videos_dir)
    processed_dir = ensure_dir(manifest.processed_dir)
    images_root = ensure_dir(processed_dir / "images")
    metadata_path = processed_dir / "frame_index.csv"

    with metadata_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "split",
                "video_id",
                "source_path",
                "frame_index",
                "timestamp_sec",
                "image_path",
            ],
        )
        writer.writeheader()
        for split, video_names in manifest.splits.items():
            split_dir = ensure_dir(images_root / split)
            for video_name in video_names:
                video_path = raw_dir / video_name
                if not video_path.exists():
                    alternate = Path(manifest.video_metadata.get(video_name, {}).get("source_path", ""))
                    video_path = alternate if alternate.exists() else video_path
                if not video_path.exists():
                    raise FileNotFoundError(f"Video listed in manifest not found: {video_name}")

                capture = cv2.VideoCapture(str(video_path))
                if not capture.isOpened():
                    raise RuntimeError(f"Failed to open video: {video_path}")

                native_fps = capture.get(cv2.CAP_PROP_FPS) or 0
                sample_interval = max(1, round(native_fps / fps)) if native_fps > 0 and fps > 0 else 1
                frame_idx = 0
                saved_count = 0
                while True:
                    ok, frame = capture.read()
                    if not ok:
                        break
                    if frame_idx % sample_interval == 0:
                        image_name = f"{Path(video_name).stem}_f{frame_idx:06d}{image_ext}"
                        image_path = split_dir / image_name
                        cv2.imwrite(str(image_path), frame)
                        writer.writerow(
                            {
                                "split": split,
                                "video_id": video_name,
                                "source_path": str(video_path.resolve()),
                                "frame_index": frame_idx,
                                "timestamp_sec": round(frame_idx / native_fps, 3) if native_fps > 0 else "",
                                "image_path": str(image_path.resolve()),
                            }
                        )
                        saved_count += 1
                        if max_frames_per_video is not None and saved_count >= max_frames_per_video:
                            break
                    frame_idx += 1
                capture.release()
    return metadata_path
