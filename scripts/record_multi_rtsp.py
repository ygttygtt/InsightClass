"""多路 RTSP 摄像头自动录制脚本

同时连接多台 Hikvision 摄像头，每路独立线程录制。支持按前后视角分组，方便多人分工。

用法:
    # 按视角分组录制全部
    python scripts/record_multi_rtsp.py --view front    # 录制全部前视角（7个）
    python scripts/record_multi_rtsp.py --view rear     # 录制全部后视角（9个）

    # 只录部分IP（output 目录按视角区分）
    python scripts/record_multi_rtsp.py --view front --ips 10.8.14.36 10.8.14.34
    python scripts/record_multi_rtsp.py --view rear --ips 10.8.14.5 10.8.14.29

    # 手动指定IP + 完全不区分视角
    python scripts/record_multi_rtsp.py --ips 10.8.14.36 10.8.14.5

    # 带预览窗口
    python scripts/record_multi_rtsp.py --view front --ips 10.8.14.36 --preview
"""

import argparse
import os
import time
from datetime import datetime
from threading import Event, Thread

import cv2

# ---------- 摄像头配置 ----------
USERNAME = "admin"
PASSWORD = "1000phone"
PORT = 554
RTSP_PATH = "/Streaming/Channels/101"  # 主码流

# 分组IP（方便多人分工录制时可以按组分配）
CAMERA_GROUPS = {
    "front": [  # 前视角
        "10.8.14.36",
        "10.8.14.34",
        "10.8.14.30",
        "10.8.14.10",
        "10.8.14.18",
        "10.8.14.26",
        "10.8.14.28",
    ],
    "rear": [   # 后视角
        "10.8.14.5",
        "10.8.14.29",
        "10.8.14.21",
        "10.8.14.19",
        "10.8.14.17",
        "10.8.14.11",
        "10.8.14.22",
        "10.8.14.24",
        "10.8.14.32",
    ],
}

BASE_OUTPUT_DIR = "data/raw_videos"

# 录制参数
RECORD_FPS = 15
RECORD_WIDTH = None   # None = 保持原始分辨率
FOURCC = "avc1"       # H.264，失败自动回退 mp4v

stop_event = Event()


def build_rtsp_url(ip: str) -> str:
    return f"rtsp://{USERNAME}:{PASSWORD}@{ip}:{PORT}{RTSP_PATH}"


def recorder_thread(ip: str, output_dir: str, show_preview: bool) -> None:
    url = build_rtsp_url(ip)
    print(f"[{ip}] 正在连接 {url} ...")

    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        print(f"[{ip}] ❌ 连接失败，跳过")
        return

    src_fps = cap.get(cv2.CAP_PROP_FPS)
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[{ip}] ✅ 连接成功  {src_w}x{src_h} @ {src_fps:.1f}FPS")

    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(output_dir, f"{ip}_{timestamp}.mp4")

    if RECORD_WIDTH:
        out_w = RECORD_WIDTH
        out_h = int(src_h * (RECORD_WIDTH / src_w))
    else:
        out_w, out_h = src_w, src_h

    fourcc = cv2.VideoWriter_fourcc(*FOURCC)
    writer = cv2.VideoWriter(out_path, fourcc, RECORD_FPS, (out_w, out_h))
    if not writer.isOpened():
        print(f"[{ip}] ⚠️ {FOURCC} 编码不可用，改用 mp4v ...")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(out_path, fourcc, RECORD_FPS, (out_w, out_h))
    if not writer.isOpened():
        print(f"[{ip}] ❌ 输出文件创建失败，跳过")
        cap.release()
        return

    print(f"[{ip}] 📹 开始录制 → {out_path}")

    frame_interval = max(1, int(src_fps / RECORD_FPS)) if src_fps > 0 else 1
    frame_count = 0
    saved_count = 0
    start_time = time.time()
    window_name = f"RTSP {ip}"

    while not stop_event.is_set():
        ret, frame = cap.read()
        if not ret:
            print(f"[{ip}] ⚠️ 视频流中断，尝试重连...")
            cap.release()
            time.sleep(2)
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not cap.isOpened():
                print(f"[{ip}] ❌ 重连失败，终止录制")
                break
            print(f"[{ip}] ✅ 重连成功")
            continue

        frame_count += 1
        if frame_count % frame_interval == 0:
            if RECORD_WIDTH:
                frame = cv2.resize(frame, (out_w, out_h))
            writer.write(frame)
            saved_count += 1

        if show_preview:
            preview = cv2.resize(frame, (min(out_w, 640), min(out_h, 360)))
            cv2.imshow(window_name, preview)
            cv2.waitKey(1)

        if frame_count % 300 == 0:
            elapsed = time.time() - start_time
            print(f"[{ip}] 已录制 {saved_count} 帧 | {elapsed:.0f}s")

    elapsed = time.time() - start_time
    cap.release()
    writer.release()
    if show_preview:
        cv2.destroyWindow(window_name)
    file_size_mb = os.path.getsize(out_path) / (1024 * 1024)
    print(f"[{ip}] ⏹️  录制结束: {saved_count} 帧 | {elapsed:.0f}s | {file_size_mb:.1f}MB → {out_path}")


def main():
    parser = argparse.ArgumentParser(
        description="多路RTSP自动录制 — 支持按前后视角分组",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python scripts/record_multi_rtsp.py --view front                  # 全部前视角
    python scripts/record_multi_rtsp.py --view rear --ips 10.8.14.5 10.8.14.29  # 后视角中的部分IP
    python scripts/record_multi_rtsp.py --ips 10.8.14.36 10.8.14.5   # 手动指定，不区分视角
        """,
    )
    parser.add_argument("--view", choices=["front", "rear"], default=None,
                        help="按视角分组: front=前视角(7个), rear=后视角(9个)。控制输出目录命名")
    parser.add_argument("--ips", nargs="+", default=None,
                        help="手动指定要录制的IP列表。不传则录制该视角下的全部IP")
    parser.add_argument("--preview", action="store_true",
                        help="显示每个摄像头的预览窗口")
    parser.add_argument("--output", default=None,
                        help="自定义输出目录（默认 data/raw_videos/{front,rear}/）")
    args = parser.parse_args()

    # 确定要录制的IP列表
    if args.ips:
        ips = args.ips
    elif args.view:
        ips = CAMERA_GROUPS[args.view]
    else:
        ips = CAMERA_GROUPS["front"] + CAMERA_GROUPS["rear"]

    # 确定输出目录和标签
    if args.output:
        output_dir = args.output
    elif args.view:
        output_dir = os.path.join(BASE_OUTPUT_DIR, args.view)
    elif args.ips:
        output_dir = os.path.join(BASE_OUTPUT_DIR, "manual")
    else:
        output_dir = os.path.join(BASE_OUTPUT_DIR, "all")

    if args.view:
        view_label = "前视角" if args.view == "front" else "后视角"
    elif args.ips:
        view_label = "手动指定"
    else:
        view_label = "全部"

    print(f"========== 多路RTSP录制 ==========")
    print(f"视角: {view_label} ({len(ips)} 个摄像头)")
    print(f"IP列表: {', '.join(ips)}")
    print(f"输出目录: {os.path.abspath(output_dir)}")
    print(f"预览窗口: {'开' if args.preview else '关'}")
    print(f"按 Ctrl+C 停止录制")
    print(f"==================================")

    threads = []
    for ip in ips:
        t = Thread(target=recorder_thread, args=(ip, output_dir, args.preview), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(0.5)

    if args.preview:
        print("\n在任意预览窗口按 'q' 键停止全部录制\n")
        while not stop_event.is_set():
            key = cv2.waitKey(500) & 0xFF
            if key == ord("q"):
                stop_event.set()
            if all(not t.is_alive() for t in threads):
                break
    else:
        try:
            while any(t.is_alive() for t in threads):
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n收到中断信号，正在停止...")

    stop_event.set()
    for t in threads:
        t.join(timeout=10)

    if args.preview:
        cv2.destroyAllWindows()

    print("\n全部录制完成。")


if __name__ == "__main__":
    main()
