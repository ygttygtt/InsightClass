"""RTSP 摄像头实时预览脚本（Hikvision DS-2CD3T35-I3）

用法:
    python scripts/rtsp_preview.py              # 交互式选择摄像头
    python scripts/rtsp_preview.py 10.8.14.36   # 直接指定 IP
"""

import cv2
import sys

# 摄像头配置
USERNAME = "admin"
PASSWORD = "1000phone"
PORT = 554
RTSP_PATH = "/Streaming/Channels/101"

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


def pick_camera() -> str:
    """交互式选择摄像头 IP。"""
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


def preview(ip: str) -> None:
    """连接摄像头并显示预览窗口。"""
    url = f"rtsp://{USERNAME}:{PASSWORD}@{ip}:{PORT}{RTSP_PATH}"
    print(f"\n正在连接 {ip} ...")

    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        print(f"无法连接 {ip}，请检查：")
        print(f"  1. 网络是否能 ping 通 {ip}")
        print("  2. 用户名/密码是否正确")
        print("  3. RTSP 端口 554 是否开放")
        return

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"连接成功  {w}x{h} @ {fps:.1f}FPS")
    print("按 Q 退出预览\n")

    window_name = f"RTSP Preview - {ip}"
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
    if len(sys.argv) > 1:
        ip = sys.argv[1]
    else:
        ip = pick_camera()

    while True:
        preview(ip)
        again = input("继续预览其他摄像头？(输入 IP/编号，直接回车退出): ").strip()
        if not again:
            break
        if again.isdigit():
            all_ips = [ip for group in CAMERA_IPS.values() for ip in group]
            idx = int(again) - 1
            if 0 <= idx < len(all_ips):
                ip = all_ips[idx]
            else:
                print("编号无效，退出")
                break
        elif again.count(".") == 3:
            ip = again
        else:
            print("输入无效，退出")
            break


if __name__ == "__main__":
    main()
