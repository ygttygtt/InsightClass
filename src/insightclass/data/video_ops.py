from __future__ import annotations

import csv
import random
from pathlib import Path

from insightclass.schemas import DatasetManifest
from insightclass.optional import require_package
from insightclass.utils.paths import ensure_dir


def _resize_frame(frame, target_width: int | None):
    """Resize frame to target width while keeping aspect ratio. Returns original if target_width is None."""
    if target_width is None:
        return frame
    import cv2

    h, w = frame.shape[:2]
    if w <= target_width:
        return frame
    scale = target_width / w
    new_h = int(h * scale)
    return cv2.resize(frame, (target_width, new_h), interpolation=cv2.INTER_AREA)


def extract_frames_from_manifest(
    manifest: DatasetManifest,
    fps: float,
    image_ext: str = ".jpg",
    max_frames_per_video: int | None = None,
    target_width: int | None = 960,
    seed: int = 42,
) -> Path:
    require_package("cv2", "Frame extraction")
    import cv2
    import gc

    raw_dir = Path(manifest.raw_videos_dir)
    processed_dir = ensure_dir(manifest.processed_dir)
    images_root = ensure_dir(processed_dir / "images")
    metadata_path = processed_dir / "frame_index.csv"
    rng = random.Random(seed)

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
                total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
                sample_interval = max(1, round(native_fps / fps)) if native_fps > 0 and fps > 0 else 1

                # Build candidate frame indices (same logic as before: evenly spaced by fps)
                candidate_indices = list(range(0, total_frames, sample_interval))

                # If max_frames_per_video is set, uniformly sample across the whole video
                if max_frames_per_video is not None and len(candidate_indices) > max_frames_per_video:
                    selected_indices = sorted(rng.sample(candidate_indices, max_frames_per_video))
                else:
                    selected_indices = candidate_indices

                # Extract only the selected frames (seek instead of decoding everything)
                saved_count = 0
                for target_idx in selected_indices:
                    capture.set(cv2.CAP_PROP_POS_FRAMES, target_idx)
                    ok, frame = capture.read()
                    if not ok:
                        continue
                    frame = _resize_frame(frame, target_width)
                    image_name = f"{Path(video_name).stem}_f{target_idx:06d}{image_ext}"
                    image_path = split_dir / image_name
                    cv2.imwrite(str(image_path), frame)
                    writer.writerow(
                        {
                            "split": split,
                            "video_id": video_name,
                            "source_path": str(video_path.resolve()),
                            "frame_index": target_idx,
                            "timestamp_sec": round(target_idx / native_fps, 3) if native_fps > 0 else "",
                            "image_path": str(image_path.resolve()),
                        }
                    )
                    saved_count += 1
                capture.release()
                del capture
                gc.collect()
                print(f"  [{split}] {video_name}: {saved_count} frames extracted (sampled from {total_frames} total)")
    return metadata_path
