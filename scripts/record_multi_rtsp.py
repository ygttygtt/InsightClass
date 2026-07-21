"""Record multiple RTSP cameras concurrently.

Camera addresses and credentials are intentionally not bundled. Pass camera
IPs explicitly and provide the password through INSIGHTCLASS_RTSP_PASSWORD or
the interactive prompt.
"""

from __future__ import annotations

import argparse
import getpass
import ipaddress
import os
import time
from datetime import datetime
from threading import Event, Lock, Thread
from urllib.parse import quote

import cv2

BASE_OUTPUT_DIR = "data/raw_videos"
RECORD_FPS = 15
RECORD_WIDTH = 960
FOURCC = "avc1"

stop_event = Event()
preview_frames: dict[str, object] = {}
preview_lock = Lock()


def build_rtsp_url(
    ip: str,
    username: str,
    password: str,
    port: int = 554,
    channel: str = "101",
) -> str:
    """Build a Hikvision-compatible RTSP URL with escaped credentials."""
    host = str(ipaddress.ip_address(ip))
    if not 1 <= int(port) <= 65535:
        raise ValueError("RTSP port must be between 1 and 65535")
    if channel not in {"101", "102"}:
        raise ValueError("RTSP channel must be 101 or 102")
    credentials = ""
    if username:
        credentials = f"{quote(username, safe='')}:{quote(password, safe='')}@"
    return f"rtsp://{credentials}{host}:{int(port)}/Streaming/Channels/{channel}"


def resolve_password(explicit: str | None, environ: dict[str, str] | None = None) -> str:
    """Resolve a password without shipping a project-wide default."""
    if explicit is not None:
        return explicit
    source = os.environ if environ is None else environ
    value = source.get("INSIGHTCLASS_RTSP_PASSWORD")
    if value is not None:
        return value
    return getpass.getpass("RTSP 密码（输入不会显示）: ")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="多路 RTSP 摄像头录制工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  $env:INSIGHTCLASS_RTSP_PASSWORD = "your-password"
  python scripts/record_multi_rtsp.py --ips 192.0.2.10 192.0.2.11
  python scripts/record_multi_rtsp.py --ips 192.0.2.10 --sub --preview
        """,
    )
    parser.add_argument("--ips", nargs="+", required=True, help="要录制的摄像头 IP 列表")
    parser.add_argument(
        "--view",
        choices=["front", "rear", "manual"],
        default="manual",
        help="输出目录分类，不再内置任何摄像头地址",
    )
    parser.add_argument(
        "--username",
        default=os.getenv("INSIGHTCLASS_RTSP_USERNAME", "admin"),
        help="RTSP 用户名（默认读取 INSIGHTCLASS_RTSP_USERNAME）",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="RTSP 密码；推荐改用 INSIGHTCLASS_RTSP_PASSWORD，避免出现在命令历史中",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("INSIGHTCLASS_RTSP_PORT", "554")),
        help="RTSP 端口（默认 554）",
    )
    parser.add_argument("--preview", action="store_true", help="显示实时预览窗口")
    parser.add_argument("--sub", action="store_true", help="使用子码流 102/H.264")
    parser.add_argument(
        "--preview-main",
        action="store_true",
        help="使用子码流录制时，另连主码流 101 用于预览",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="输出目录（默认 data/raw_videos/<view>/）",
    )
    return parser


def recorder_thread(
    ip: str,
    output_dir: str,
    username: str,
    password: str,
    port: int,
    use_sub: bool = False,
    preview_main: bool = False,
) -> None:
    channel = "102" if use_sub else "101"
    url = build_rtsp_url(ip, username, password, port, channel)
    stream_label = "子码流(102)" if use_sub else "主码流(101)"
    print(f"[{ip}] 正在连接 {stream_label} ...")

    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not cap.isOpened():
        print(f"[{ip}] [FAIL] 连接失败，跳过")
        return

    src_fps = cap.get(cv2.CAP_PROP_FPS)
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if src_w <= 0 or src_h <= 0:
        print(f"[{ip}] [FAIL] 摄像头未返回有效分辨率")
        cap.release()
        return
    print(f"[{ip}] [OK] {src_w}x{src_h} @ {src_fps:.1f} FPS")

    preview_cap = None
    if preview_main and use_sub:
        preview_url = build_rtsp_url(ip, username, password, port, "101")
        preview_cap = cv2.VideoCapture(preview_url, cv2.CAP_FFMPEG)
        preview_cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not preview_cap.isOpened():
            print(f"[{ip}] [WARN] 主码流预览连接失败，改用录制码流预览")
            preview_cap.release()
            preview_cap = None

    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(output_dir, f"{ip}_{timestamp}.mp4")
    out_w = RECORD_WIDTH if RECORD_WIDTH else src_w
    out_h = int(src_h * (out_w / src_w)) if RECORD_WIDTH else src_h

    writer = cv2.VideoWriter(
        out_path,
        cv2.VideoWriter_fourcc(*FOURCC),
        RECORD_FPS,
        (out_w, out_h),
    )
    if not writer.isOpened():
        print(f"[{ip}] [WARN] {FOURCC} 不可用，回退到 mp4v")
        writer = cv2.VideoWriter(
            out_path,
            cv2.VideoWriter_fourcc(*"mp4v"),
            RECORD_FPS,
            (out_w, out_h),
        )
    if not writer.isOpened():
        print(f"[{ip}] [FAIL] 无法创建输出文件")
        cap.release()
        if preview_cap is not None:
            preview_cap.release()
        return

    print(f"[{ip}] [REC] {out_path}")
    frame_interval = max(1, int(src_fps / RECORD_FPS)) if src_fps > 0 else 1
    frame_count = 0
    saved_count = 0
    start_time = time.time()

    while not stop_event.is_set():
        ret, frame = cap.read()
        if not ret or frame is None:
            print(f"[{ip}] [WARN] 码流中断，2 秒后重连")
            cap.release()
            time.sleep(2)
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not cap.isOpened():
                print(f"[{ip}] [FAIL] 重连失败，终止录制")
                break
            continue

        frame_count += 1
        if frame_count % frame_interval == 0:
            if RECORD_WIDTH:
                frame = cv2.resize(frame, (out_w, out_h))
            writer.write(frame)
            saved_count += 1

        if preview_cap is not None:
            preview_ok, preview_frame = preview_cap.read()
            if preview_ok and preview_frame is not None:
                with preview_lock:
                    preview_frames[ip] = preview_frame
        else:
            with preview_lock:
                preview_frames[ip] = frame

        if frame_count % 300 == 0:
            print(f"[{ip}] 已录制 {saved_count} 帧 | {time.time() - start_time:.0f}s")

    elapsed = time.time() - start_time
    cap.release()
    if preview_cap is not None:
        preview_cap.release()
    writer.release()
    with preview_lock:
        preview_frames.pop(ip, None)
    file_size_mb = os.path.getsize(out_path) / (1024 * 1024) if os.path.exists(out_path) else 0
    print(
        f"[{ip}] [STOP] {saved_count} 帧 | {elapsed:.0f}s | "
        f"{file_size_mb:.1f} MiB -> {out_path}"
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        ips = [str(ipaddress.ip_address(value)) for value in args.ips]
        if not 1 <= args.port <= 65535:
            raise ValueError("RTSP 端口必须在 1 到 65535 之间")
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    password = resolve_password(args.password) if args.username else ""
    output_dir = args.output or os.path.join(BASE_OUTPUT_DIR, args.view)
    use_sub = args.sub or args.preview
    if args.preview and not args.sub:
        print("[INFO] 预览模式使用子码流 102，以提高 OpenCV 兼容性")

    stop_event.clear()
    print("========== 多路 RTSP 录制 ==========")
    print(f"分类: {args.view} | 摄像头: {len(ips)} | 端口: {args.port}")
    print(f"IP: {', '.join(ips)}")
    print(f"输出: {os.path.abspath(output_dir)}")
    print(f"码流: {'102/H.264' if use_sub else '101/主码流'}")
    print("按 Ctrl+C 停止录制")

    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
    threads = []
    for ip in ips:
        thread = Thread(
            target=recorder_thread,
            args=(
                ip,
                output_dir,
                args.username,
                password,
                args.port,
                use_sub,
                args.preview_main and args.preview,
            ),
            daemon=True,
        )
        thread.start()
        threads.append(thread)
        time.sleep(0.5)

    try:
        if args.preview:
            print("按 Q 停止全部录制")
            while not stop_event.is_set():
                with preview_lock:
                    frames_copy = dict(preview_frames)
                for ip, frame in frames_copy.items():
                    cv2.imshow(f"RTSP {ip}", frame)
                if cv2.waitKey(50) & 0xFF == ord("q"):
                    break
                if all(not thread.is_alive() for thread in threads):
                    break
        else:
            while any(thread.is_alive() for thread in threads):
                time.sleep(1)
    except KeyboardInterrupt:
        print("\n收到中断信号，正在停止...")
    finally:
        stop_event.set()
        for thread in threads:
            thread.join(timeout=10)
        if args.preview:
            cv2.destroyAllWindows()
    print("全部录制完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
