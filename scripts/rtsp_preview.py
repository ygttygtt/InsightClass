"""Diagnose and preview a single RTSP camera without bundled credentials."""

from __future__ import annotations

import argparse
import getpass
import ipaddress
import os
from urllib.parse import quote

import cv2


def build_rtsp_url(
    ip: str,
    username: str,
    password: str,
    port: int = 554,
    channel: str = "101",
) -> str:
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
    if explicit is not None:
        return explicit
    source = os.environ if environ is None else environ
    value = source.get("INSIGHTCLASS_RTSP_PASSWORD")
    if value is not None:
        return value
    return getpass.getpass("RTSP 密码（输入不会显示）: ")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RTSP 摄像头诊断与预览工具")
    parser.add_argument("ip", help="摄像头 IP 地址")
    parser.add_argument(
        "--username",
        default=os.getenv("INSIGHTCLASS_RTSP_USERNAME", "admin"),
        help="RTSP 用户名（默认读取 INSIGHTCLASS_RTSP_USERNAME）",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="RTSP 密码；推荐改用 INSIGHTCLASS_RTSP_PASSWORD",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("INSIGHTCLASS_RTSP_PORT", "554")),
        help="RTSP 端口（默认 554）",
    )
    parser.add_argument("--sub", action="store_true", help="优先预览子码流 102")
    return parser


def diagnose(ip: str, username: str, password: str, port: int, channel: str) -> bool:
    url = build_rtsp_url(ip, username, password, port, channel)
    print(f"\n[Channel {channel}] 正在连接...")
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        print("  连接失败")
        return False

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"  分辨率: {width}x{height} | FPS: {fps:.1f}")
    valid_frames = 0
    for index in range(10):
        ok, frame = cap.read()
        if not ok or frame is None:
            print(f"  第 {index + 1} 帧: 读取失败")
            continue
        mean_value = float(frame.mean())
        status = "正常" if mean_value > 5 else "黑帧"
        print(f"  第 {index + 1} 帧: 像素均值={mean_value:.1f} [{status}]")
        if mean_value > 5:
            valid_frames += 1
    cap.release()
    return valid_frames >= 3


def preview(
    ip: str,
    username: str,
    password: str,
    port: int,
    channel: str,
) -> None:
    url = build_rtsp_url(ip, username, password, port, channel)
    print(f"\n正在预览 Channel {channel}，按 Q 退出")
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        print("连接失败")
        return
    window_name = f"RTSP {ip} Ch{channel}"
    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            print("视频流中断")
            break
        cv2.imshow(window_name, frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    cap.release()
    cv2.destroyWindow(window_name)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        ip = str(ipaddress.ip_address(args.ip))
        if not 1 <= args.port <= 65535:
            raise ValueError("RTSP 端口必须在 1 到 65535 之间")
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    password = resolve_password(args.password) if args.username else ""
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

    print(f"\n===== 诊断 {ip} =====")
    channel_101_ok = diagnose(ip, args.username, password, args.port, "101")
    channel_102_ok = diagnose(ip, args.username, password, args.port, "102")
    if args.sub and channel_102_ok:
        chosen = "102"
    elif channel_101_ok:
        chosen = "101"
    elif channel_102_ok:
        chosen = "102"
        print("\n主码流不可用，自动切换到子码流")
    else:
        print("\n两个码流均不可用，请检查网络、凭据和摄像头配置")
        return 1
    preview(ip, args.username, password, args.port, chosen)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
