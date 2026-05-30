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

    # 黑屏? 用子码流 (H.264)
    python scripts/record_multi_rtsp.py --view front --ips 10.8.14.34 --sub --preview

    # 录制用子码流 + 预览用主码流 (高清预览)
    python scripts/record_multi_rtsp.py --view front --ips 10.8.14.34 --preview --preview-main
"""

import argparse
import os
import time
from datetime import datetime
from threading import Event, Lock, Thread

import cv2

# ---------- 摄像头配置 ----------
USERNAME = "admin"
PASSWORD = "1000phone"
PORT = 554
RTSP_PATH = "/Streaming/Channels/101"  # 主码流 (通常 H.265)
RTSP_PATH_SUB = "/Streaming/Channels/102"  # 子码流 (通常 H.264，兼容性更好)

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
RECORD_WIDTH = 960     # 对齐抽帧脚本 --target-width 960，训练 imgsz=960
                       # 原始 1080p → 960x540，体积约降至 1/4
FOURCC = "avc1"        # H.264，失败自动回退 mp4v

stop_event = Event()
# 预览帧共享: 子线程写入，主线程读取并显示 (Windows 上 imshow 必须在主线程)
preview_frames: dict[str, any] = {}
preview_lock = Lock()


def build_rtsp_url(ip: str) -> str:
    return f"rtsp://{USERNAME}:{PASSWORD}@{ip}:{PORT}{RTSP_PATH}"


def recorder_thread(ip: str, output_dir: str, use_sub: bool = False, preview_main: bool = False) -> None:
    path = RTSP_PATH_SUB if use_sub else RTSP_PATH
    url = f"rtsp://{USERNAME}:{PASSWORD}@{ip}:{PORT}{path}"
    stream_label = "子码流(102)" if use_sub else "主码流(101)"
    print(f"[{ip}] 正在连接 {stream_label} {url} ...")

    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        print(f"[{ip}] ❌ 连接失败，跳过")
        return

    src_fps = cap.get(cv2.CAP_PROP_FPS)
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[{ip}] ✅ 连接成功  {src_w}x{src_h} @ {src_fps:.1f}FPS")

    # 预览用主码流(高清)，录制用子码流(兼容)
    preview_cap = None
    if preview_main and use_sub:
        main_url = f"rtsp://{USERNAME}:{PASSWORD}@{ip}:{PORT}{RTSP_PATH}"
        preview_cap = cv2.VideoCapture(main_url, cv2.CAP_FFMPEG)
        preview_cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if preview_cap.isOpened():
            pw = int(preview_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            ph = int(preview_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(f"[{ip}] 📺 预览已连接主码流 {pw}x{ph}")
        else:
            print(f"[{ip}] ⚠️ 主码流预览连接失败，使用子码流预览")
            preview_cap = None

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

        # 把最新帧放入共享字典，主线程负责显示
        if preview_cap is not None:
            ret_p, preview_frame = preview_cap.read()
            if ret_p:
                with preview_lock:
                    preview_frames[ip] = preview_frame
        else:
            with preview_lock:
                preview_frames[ip] = frame

        if frame_count % 300 == 0:
            elapsed = time.time() - start_time
            print(f"[{ip}] 已录制 {saved_count} 帧 | {elapsed:.0f}s")

    elapsed = time.time() - start_time
    cap.release()
    if preview_cap is not None:
        preview_cap.release()
    writer.release()
    # 清理预览帧
    with preview_lock:
        preview_frames.pop(ip, None)
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
    parser.add_argument("--sub", action="store_true",
                        help="使用子码流(102/H.264)替代主码流(101/H.265)，解决黑屏问题")
    parser.add_argument("--preview-main", action="store_true",
                        help="预览用主码流(高清)，录制用子码流(兼容)。需要同时连两路流")
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

    # --preview 自动启用子码流 (主码流 H.265 在 OpenCV 中无法正常预览)
    use_sub = args.sub
    if args.preview and not use_sub:
        print("⚠️  预览模式自动启用子码流(102)，主码流(H.265)在 OpenCV 中会黑屏")
        use_sub = True

    print(f"========== 多路RTSP录制 ==========")
    print(f"视角: {view_label} ({len(ips)} 个摄像头)")
    print(f"IP列表: {', '.join(ips)}")
    print(f"输出目录: {os.path.abspath(output_dir)}")
    print(f"码流: {'子码流(102/H.264)' if use_sub else '主码流(101/H.265)'}")
    print(f"预览窗口: {'开' if args.preview else '关'}")
    print(f"按 Ctrl+C 停止录制")
    print(f"==================================")

    # FFMPEG 使用 TCP 传输 RTSP（比 UDP 更稳定，减少黑帧）
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

    threads = []
    for ip in ips:
        t = Thread(target=recorder_thread, args=(ip, output_dir, use_sub, args.preview_main and args.preview), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(0.5)

    if args.preview:
        print("\n按 'q' 键停止全部录制\n")
        while not stop_event.is_set():
            # 主线程负责所有 GUI 操作 (Windows 上 imshow 必须在主线程)
            with preview_lock:
                frames_copy = dict(preview_frames)
            for ip, frame in frames_copy.items():
                cv2.imshow(f"RTSP {ip}", frame)
            key = cv2.waitKey(50) & 0xFF
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
