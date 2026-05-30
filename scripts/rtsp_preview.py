"""RTSP 摄像头实时预览脚本

用法:
    python scripts/rtsp_preview.py              # 交互式选择摄像头
    python scripts/rtsp_preview.py 10.8.14.34   # 直接指定 IP
    python scripts/rtsp_preview.py 10.8.14.34 --sub  # 用子码流(102)
"""

import cv2
import os
import sys

USERNAME = "admin"
PASSWORD = "1000phone"
PORT = 554

CAMERA_IPS = {
    "前视角": [
        "10.8.14.36", "10.8.14.34", "10.8.14.30", "10.8.14.10",
        "10.8.14.18", "10.8.14.26", "10.8.14.28",
    ],
    "后视角": [
        "10.8.14.5", "10.8.14.29", "10.8.14.21", "10.8.14.19",
        "10.8.14.17", "10.8.14.11", "10.8.14.22", "10.8.14.24", "10.8.14.32",
    ],
}

os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"


def pick_camera() -> str:
    all_ips = []
    print("\n可用摄像头：")
    for group, ips in CAMERA_IPS.items():
        print(f"\n  [{group}]")
        for i, ip in enumerate(ips, 1):
            idx = len(all_ips)
            all_ips.append(ip)
            print(f"    {idx + 1:2d}. {ip}")
    print()
    while True:
        raw = input("输入编号或 IP 地址（直接回车连 10.8.14.34）: ").strip()
        if not raw:
            return "10.8.14.34"
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(all_ips):
                return all_ips[idx]
            print(f"  编号超出范围，请输入 1-{len(all_ips)}")
        elif raw.count(".") == 3:
            return raw
        else:
            print("  请输入有效的编号或 IP 地址")


def diagnose(ip: str, channel: str) -> bool:
    """连接指定 channel，读几帧诊断。返回 True 表示画面正常。"""
    url = f"rtsp://{USERNAME}:{PASSWORD}@{ip}:{PORT}/Streaming/Channels/{channel}"
    print(f"\n[Channel {channel}] {url}")

    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        print("  连接失败")
        return False

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"  分辨率: {w}x{h}  FPS: {fps}")

    ok_count = 0
    for i in range(10):
        ret, frame = cap.read()
        if not ret:
            print(f"  第{i+1}帧: 读取失败")
            continue
        mean_val = frame.mean()
        status = "正常" if mean_val > 5 else "黑帧"
        print(f"  第{i+1}帧: 像素均值={mean_val:.1f} [{status}]")
        if mean_val > 5:
            ok_count += 1

    cap.release()
    return ok_count >= 3


def preview(ip: str, channel: str) -> None:
    url = f"rtsp://{USERNAME}:{PASSWORD}@{ip}:{PORT}/Streaming/Channels/{channel}"
    print(f"\n正在连接 Channel {channel} ...")

    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        print("连接失败")
        return

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"连接成功  {w}x{h} @ {fps:.1f}FPS")
    print("按 Q 退出预览\n")

    window_name = f"RTSP {ip} Ch{channel}"
    while True:
        ret, frame = cap.read()
        if not ret:
            print("视频流中断")
            break
        cv2.imshow(window_name, frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyWindow(window_name)


def main():
    use_sub = "--sub" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--sub"]

    if args:
        ip = args[0]
    else:
        ip = pick_camera()

    # 先诊断两个 channel
    print(f"\n===== 诊断 {ip} =====")
    ch101_ok = diagnose(ip, "101")
    ch102_ok = diagnose(ip, "102")

    if use_sub:
        chosen = "102"
    elif ch101_ok:
        chosen = "101"
    elif ch102_ok:
        chosen = "102"
        print(f"\n主码流(101)黑屏，自动切换到子码流(102)")
    else:
        print(f"\n两个 channel 都无法获取正常画面，请检查摄像头")
        return

    print(f"\n===== 预览 Channel {chosen} =====")
    preview(ip, chosen)


if __name__ == "__main__":
    main()
