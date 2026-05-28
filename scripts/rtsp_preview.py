"""RTSP 摄像头实时预览脚本（Hikvision DS-2CD3T35-I3）"""

import cv2
import sys

# 摄像头配置
RTSP_URL = "rtsp://admin:1000phone@10.8.14.34:554/Streaming/Channels/101"


def main():
    print(f"正在连接: {RTSP_URL}")
    cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)

    if not cap.isOpened():
        print("无法连接摄像头，请检查：")
        print("  1. 网络是否能 ping 通 10.8.14.34")
        print("  2. 用户名/密码是否正确")
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
