"""
将 X-AnyLabeling 标注结果整理为 YOLO 训练格式。

用法:
    conda run -n <your-env-name> python scripts/prepare_dataset.py

输入:
    data/labels_01/          — X-AnyLabeling 导出的 jpg + txt 混合目录

输出:
    data/processed/classroom_behavior_v1/
    ├── images/
    │   ├── train/
    │   └── test/
    ├── labels/
    │   ├── train/
    │   └── test/
    └── yolo_dataset.yaml
"""

import os
import random
import shutil
from pathlib import Path

# ── 配置 ──────────────────────────────────────────────────
SRC_DIR = Path("data/labels_01")
OUT_DIR = Path("data/processed/classroom_behavior_v1")
TEST_RATIO = 0.10       # 10% 测试集
SEED = 42               # 固定随机种子，保证可复现
# ──────────────────────────────────────────────────────────


def collect_samples(src: Path) -> dict[str, list[tuple[Path, Path]]]:
    """按视频 ID 分组收集样本 (jpg, txt) 对。"""
    videos: dict[str, list[tuple[Path, Path]]] = {}
    for txt_path in sorted(src.glob("*.txt")):
        stem = txt_path.stem
        jpg_path = src / f"{stem}.jpg"
        if not jpg_path.exists():
            print(f"  [跳过] 缺少图片: {jpg_path}")
            continue
        # 从文件名提取视频 ID，例如 classroom_003_f002040 → classroom_003
        video_id = stem.rsplit("_f", 1)[0]
        videos.setdefault(video_id, []).append((jpg_path, txt_path))
    return videos


def split_videos(videos: dict, ratio: float, seed: int) -> tuple[list[str], list[str]]:
    """按视频级别做 train/test 切分，防止同一视频的帧泄漏到不同集合。"""
    video_ids = sorted(videos.keys())
    rng = random.Random(seed)
    shuffled = video_ids[:]
    rng.shuffle(shuffled)
    n_test = max(1, round(len(shuffled) * ratio))
    test_ids = set(shuffled[:n_test])
    train_ids = [v for v in shuffled if v not in test_ids]
    test_ids_list = [v for v in shuffled if v in test_ids]
    return train_ids, test_ids_list


def copy_samples(videos: dict, video_ids: list[str], split: str, out: Path):
    """把指定视频的帧复制到 images/{split} 和 labels/{split}。"""
    img_dir = out / "images" / split
    lbl_dir = out / "labels" / split
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for vid in video_ids:
        for jpg, txt in videos[vid]:
            shutil.copy2(jpg, img_dir / jpg.name)
            shutil.copy2(txt, lbl_dir / txt.name)
            count += 1
    return count


def write_yolo_yaml(out: Path, train_count: int, test_count: int):
    """生成 Ultralytics 兼容的 yolo_dataset.yaml。"""
    yaml_content = f"""\
# YOLO 数据集配置 — 由 scripts/prepare_dataset.py 自动生成
path: {out.as_posix()}
train: images/train
val: images/test

names:
  0: phone_use
  1: talking
  2: sleeping

# 数据集统计
# train: {train_count} 张图片
# test:  {test_count} 张图片
"""
    yaml_path = out / "yolo_dataset.yaml"
    yaml_path.write_text(yaml_content, encoding="utf-8")
    return yaml_path


def main():
    print("=" * 60)
    print("InsightClass 数据集整理工具")
    print("=" * 60)

    # 1. 收集样本
    print(f"\n[1/4] 扫描源目录: {SRC_DIR}")
    videos = collect_samples(SRC_DIR)
    total_frames = sum(len(v) for v in videos.values())
    print(f"  找到 {len(videos)} 个视频，共 {total_frames} 帧")

    # 2. 按视频切分
    print(f"\n[2/4] 按视频级别切分 (test_ratio={TEST_RATIO}, seed={SEED})")
    train_ids, test_ids = split_videos(videos, TEST_RATIO, SEED)
    train_count = sum(len(videos[v]) for v in train_ids)
    test_count = sum(len(videos[v]) for v in test_ids)
    print(f"  训练集: {len(train_ids)} 个视频, {train_count} 帧  {train_ids}")
    print(f"  测试集: {len(test_ids)} 个视频, {test_count} 帧  {test_ids}")

    # 3. 复制文件
    print(f"\n[3/4] 复制文件到: {OUT_DIR}")
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
        print("  已清理旧目录")

    copy_samples(videos, train_ids, "train", OUT_DIR)
    copy_samples(videos, test_ids, "test", OUT_DIR)
    print(f"  train: {train_count} 张图片 + 标签")
    print(f"  test:  {test_count} 张图片 + 标签")

    # 4. 生成 yolo_dataset.yaml
    print(f"\n[4/4] 生成 YOLO 配置文件")
    yaml_path = write_yolo_yaml(OUT_DIR, train_count, test_count)
    print(f"  写入: {yaml_path}")

    # 5. 统计标签分布
    print(f"\n{'=' * 60}")
    print("标签分布统计:")
    class_counts = {0: 0, 1: 0, 2: 0}
    class_names = {0: "phone_use", 1: "talking", 2: "sleeping"}
    for split_videos_list in [train_ids, test_ids]:
        for vid in split_videos_list:
            for _, txt in videos[vid]:
                for line in txt.read_text().strip().splitlines():
                    if line.strip():
                        cid = int(line.split()[0])
                        class_counts[cid] = class_counts.get(cid, 0) + 1

    total_boxes = sum(class_counts.values())
    for cid, count in sorted(class_counts.items()):
        pct = count / total_boxes * 100 if total_boxes else 0
        print(f"  {class_names[cid]:12s} (id={cid}): {count:4d} 个框 ({pct:.1f}%)")
    print(f"  {'总计':12s}:       {total_boxes:4d} 个框")

    print(f"\n{'=' * 60}")
    print("完成! 数据集已准备好，可以开始训练:")
    print(f"  conda run -n <your-env-name> python -m insightclass train --config configs/training.yaml")
    print("=" * 60)


if __name__ == "__main__":
    main()
