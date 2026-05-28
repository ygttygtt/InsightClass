"""Uniformly sample 25 frames per video into a single annotation directory."""
import cv2
import random
import os

raw_dir = "data/raw_videos"
out_dir = "data/labeling/batch_01_annot"
os.makedirs(out_dir, exist_ok=True)

videos = sorted(f for f in os.listdir(raw_dir) if f.endswith((".mkv", ".mp4", ".avi")))
rng = random.Random(42)
total_saved = 0

for vname in videos:
    cap = cv2.VideoCapture(os.path.join(raw_dir, vname))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    native_fps = cap.get(cv2.CAP_PROP_FPS)
    step = max(1, round(native_fps * 2))  # candidate every ~2 seconds
    candidates = list(range(0, total_frames, step))
    selected = sorted(rng.sample(candidates, min(25, len(candidates))))
    stem = os.path.splitext(vname)[0]
    saved = 0
    for idx in selected:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        if w > 960:
            scale = 960 / w
            frame = cv2.resize(frame, (960, int(h * scale)), interpolation=cv2.INTER_AREA)
        fname = f"{stem}_f{idx:06d}.jpg"
        cv2.imwrite(os.path.join(out_dir, fname), frame)
        saved += 1
    cap.release()
    total_saved += saved
    print(f"{vname}: {saved} frames (from {total_frames} total)")

print(f"\nTotal: {total_saved} frames in {out_dir}")
