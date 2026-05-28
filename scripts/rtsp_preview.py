"""RTSP 摄像头实时预览脚本（Hikvision DS-2CD3T35-I3）"""

import cv2
import os
import sys

# 摄像头配置 — 通过环境变量设置，或在命令行传入 IP
RTSP_USERNAME = os.environ.get("RTSP_USERNAME", "admin")
RTSP_PASSWORD = os.environ.get("RTSP_PASSWORD", "")


def main():
    ip = sys.argv[1] if len(sys.argv) > 1 else "10.8.14.34"
    rtsp_url = f"rtsp://{RTSP_USERNAME}:{RTSP_PASSWORD}@{ip}:554/Streaming/Channels/101"
    print(f"正在连接: {rtsp_url}")
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

    if not cap.isOpened():
        print("无法连接摄像头，请检查：")
        print(f"  1. 网络是否能 ping 通 {ip}")
        print("  2. 用户名/密码是否正确（通过 RTSP_USERNAME / RTSP_PASSWORD 环境变量设置）")
        print("  3. RTSP 端口 554 是否开放")
        sys.exit(1)

    print("连接成功，按 q 退出预览")
    while True:
        ret, frame = cap.read()
        if not ret:
            print("视频流中断")
            break
        cv2.imshow("RTSP Preview", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
