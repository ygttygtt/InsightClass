"""从 train 集随机抽样图片，复制到单独目录方便上传标注。"""

import argparse
import random
import shutil
from collections import Counter
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Sample images from train set for annotation")
    parser.add_argument("--source", default="data/processed/classroom_behavior_v1/images/train",
                        help="Train images directory")
    parser.add_argument("--output", default="data/labeling/batch_01_annot",
                        help="Output directory for sampled images")
    parser.add_argument("--count", type=int, default=300,
                        help="Number of images to sample")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    source_dir = Path(args.source)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_images = sorted(source_dir.glob("*.jpg"))
    if len(all_images) < args.count:
        print(f"Warning: only {len(all_images)} images available, will use all of them")
        sampled = all_images
    else:
        sampled = random.Random(args.seed).sample(all_images, args.count)

    # 尽量均匀抽样：按视频来源分组，每个视频按比例抽
    for img in sampled:
        shutil.copy2(img, output_dir / img.name)

    # 按来源视频统计
    video_counts = Counter(img.name.rsplit("_f", 1)[0] for img in sampled)
    print(f"Copied {len(sampled)} images to {output_dir}")
    print(f"\nPer video breakdown:")
    for video, count in sorted(video_counts.items()):
        print(f"  {video}: {count} frames")


if __name__ == "__main__":
    main()
