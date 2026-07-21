import sys

def test_environment():
    print("=" * 60)
    print("Python 深度学习环境测试")
    print("=" * 60)

    print(f"\nPython 版本: {sys.version}")

    try:
        import torch
        print(f"\nPyTorch 版本: {torch.__version__}")
        print(f"CUDA 可用: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"CUDA 版本: {torch.version.cuda}")
            print(f"GPU 设备: {torch.cuda.get_device_name(0)}")
            print(f"GPU 数量: {torch.cuda.device_count()}")
            x = torch.rand(3, 3).cuda()
            print(f"GPU 张量计算测试: 通过")
        else:
            print("当前使用 CPU 模式")
            x = torch.rand(3, 3)
            print(f"CPU 张量计算测试: 通过")
    except ImportError:
        print("\nPyTorch: 未安装")

    try:
        import numpy as np
        print(f"\nNumPy 版本: {np.__version__}")
    except ImportError:
        print("\nNumPy: 未安装")

    try:
        import yaml
        print(f"PyYAML 版本: {yaml.__version__}")
    except ImportError:
        print("PyYAML: 未安装")

    try:
        import cv2
        print(f"OpenCV 版本: {cv2.__version__}")
    except ImportError:
        print("OpenCV: 未安装")

    try:
        import ultralytics
        print(f"Ultralytics 版本: {ultralytics.__version__}")
    except ImportError:
        print("Ultralytics: 未安装")

    try:
        import supervision
        print(f"Supervision 版本: {supervision.__version__}")
    except ImportError:
        print("Supervision: 未安装")

    print("\n" + "=" * 60)
    print("环境测试完成")
    print("=" * 60)


if __name__ == "__main__":
    test_environment()
